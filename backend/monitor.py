"""Monitor 24/7: descarga velas, calcula RSI, detecta señales y dispara alarmas."""
import os
import time
import asyncio
import logging

import httpx

from . import store, notify
from .indicators import rsi_series, detect_divergence, atr

log = logging.getLogger("monitor")

DATA_BASE = os.environ.get("DATA_BASE", "https://api.binance.com")

# memoria por activo entre ciclos
_mem = {}  # symbol -> {prev_rsi, prev_zone, last_alert, last_div}

# prioridad de señales (la más alta gana cuando coinciden en el mismo ciclo)
PRIORITY = {"divergence": 4, "turn": 3, "exit": 2, "simple": 1}

LABELS = {
    "simple": "Entrada en zona",
    "turn": "Giro en zona",
    "exit": "Salida de zona",
    "divergence": "Divergencia",
}


async def fetch_ohlc(client, symbol, interval, limit=200):
    """Devuelve (highs, lows, closes) de velas cerradas (descarta la vela en formación)."""
    r = await client.get(
        f"{DATA_BASE}/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=12,
    )
    r.raise_for_status()
    klines = r.json()
    closed = klines[:-1]  # anti-repintado
    highs = [float(k[2]) for k in closed]
    lows = [float(k[3]) for k in closed]
    closes = [float(k[4]) for k in closed]
    return highs, lows, closes


async def fetch_closes(client, symbol, interval, limit=200):
    _, _, closes = await fetch_ohlc(client, symbol, interval, limit)
    return closes


def _zone(rsi_val, oversold, overbought):
    if rsi_val <= oversold:
        return "oversold"
    if rsi_val >= overbought:
        return "overbought"
    return "neutral"


def _in_quiet_hours(schedule):
    if not schedule.get("enabled"):
        return False
    now = time.localtime()
    cur = now.tm_hour * 60 + now.tm_min
    try:
        sh, sm = map(int, schedule["quiet_start"].split(":"))
        eh, em = map(int, schedule["quiet_end"].split(":"))
    except (ValueError, KeyError):
        return False
    start, end = sh * 60 + sm, eh * 60 + em
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end  # cruza medianoche


def _detect(symbol, rsi_now, prev_rsi, zone, prev_zone, signals_cfg, div):
    """Devuelve (kind, side) de la señal de mayor prioridad activa, o (None, None)."""
    candidates = []

    if signals_cfg.get("divergence") and div:
        candidates.append(("divergence", "buy" if div == "bullish" else "sell"))

    if signals_cfg.get("turn") and prev_rsi is not None:
        if zone == "oversold" and rsi_now > prev_rsi:
            candidates.append(("turn", "buy"))
        elif zone == "overbought" and rsi_now < prev_rsi:
            candidates.append(("turn", "sell"))

    if signals_cfg.get("exit"):
        if prev_zone == "oversold" and zone == "neutral":
            candidates.append(("exit", "buy"))
        elif prev_zone == "overbought" and zone == "neutral":
            candidates.append(("exit", "sell"))

    if signals_cfg.get("simple") and zone != "neutral" and prev_zone != zone:
        candidates.append(("simple", "buy" if zone == "oversold" else "sell"))

    if not candidates:
        return None, None
    return max(candidates, key=lambda c: PRIORITY[c[0]])


async def _process_asset(client, symbol, cfg):
    acfg = cfg["assets"][symbol]
    if not acfg.get("enabled"):
        return
    mem = _mem.setdefault(symbol, {"prev_rsi": None, "prev_zone": None, "last_alert": 0, "last_div": None})

    try:
        highs, lows, closes = await fetch_ohlc(client, symbol, cfg["interval"])
    except Exception as e:  # noqa: BLE001
        log.error("[%s] datos: %s", symbol, e)
        store.STATE["assets"].setdefault(symbol, {})["error"] = "sin datos"
        return

    rsis = rsi_series(closes, cfg["rsi_period"])
    rsi_now = rsis[-1]
    if rsi_now is None:
        return
    price = closes[-1]
    zone = _zone(rsi_now, acfg["oversold"], acfg["overbought"])

    mtf_rsi = None
    if cfg.get("mtf_filter"):
        try:
            mtf_closes = await fetch_closes(client, symbol, cfg["mtf_interval"], limit=100)
            mtf_rsi = rsi_series(mtf_closes, cfg["rsi_period"])[-1]
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] MTF: %s", symbol, e)

    div = detect_divergence(closes, rsis)
    kind, side = _detect(symbol, rsi_now, mem["prev_rsi"], zone, mem["prev_zone"], acfg["signals"], div)

    # filtro anti-tendencia: compra solo si la TF mayor acompaña (RSI>=50) y venta si RSI<=50
    blocked = False
    if kind and cfg.get("mtf_filter") and mtf_rsi is not None:
        if side == "buy" and mtf_rsi < 50:
            blocked = True
        elif side == "sell" and mtf_rsi > 50:
            blocked = True

    # publicar estado en vivo (siempre)
    spark = [round(c, 6) for c in closes[-40:]]
    store.STATE["assets"][symbol] = {
        "rsi": round(rsi_now, 2),
        "mtf_rsi": round(mtf_rsi, 2) if mtf_rsi is not None else None,
        "price": price,
        "zone": zone,
        "spark": spark,
        "updated": int(time.time()),
        "error": None,
    }

    # disparar alarma
    now = time.time()
    new_div = div if kind == "divergence" else mem["last_div"]
    if kind and not blocked and (now - mem["last_alert"]) >= acfg["cooldown_seconds"]:
        # no repetir la misma divergencia consecutiva
        if not (kind == "divergence" and div == mem["last_div"]):
            atr_val = atr(highs, lows, closes, cfg.get("atr_period", 14))
            levels = _levels(price, side, atr_val, cfg)
            await _fire(client, cfg, symbol, kind, side, rsi_now, mtf_rsi, price, levels)
            mem["last_alert"] = now

    mem["prev_rsi"] = rsi_now
    mem["prev_zone"] = zone
    mem["last_div"] = new_div if div else None


def _fmt(v):
    """Formatea un precio con precisión razonable según su magnitud."""
    if v is None:
        return "—"
    if v >= 100:
        return f"{v:.2f}"
    if v >= 1:
        return f"{v:.3f}"
    return f"{v:.5f}"


def _levels(price, side, atr_val, cfg):
    """Calcula stop, take-profit y R:R a partir del ATR. None si no hay ATR."""
    if not atr_val or atr_val <= 0:
        return None
    mult = float(cfg.get("stop_atr_mult", 1.5))
    rr = float(cfg.get("rr_ratio", 2.0))
    risk = mult * atr_val
    if side == "buy":
        stop = price - risk
        tp = price + rr * risk
    else:
        stop = price + risk
        tp = price - rr * risk
    return {
        "entry": price,
        "stop": round(stop, 8),
        "tp": round(tp, 8),
        "atr": round(atr_val, 8),
        "rr": rr,
    }


async def _fire(client, cfg, symbol, kind, side, rsi_now, mtf_rsi, price, levels=None):
    base = symbol.replace("USDT", "")
    action = "COMPRA" if side == "buy" else "VENTA"
    emoji = "🟢" if side == "buy" else "🔴"
    label = LABELS[kind]
    mtf_txt = f" · {cfg['mtf_interval']} RSI {mtf_rsi:.0f}" if mtf_rsi is not None else ""

    entry = {
        "ts": int(time.time()),
        "time": time.strftime("%d/%m %H:%M", time.localtime()),
        "symbol": symbol,
        "base": base,
        "kind": kind,
        "label": label,
        "side": side,
        "action": action,
        "rsi": round(rsi_now, 1),
        "price": price,
        "levels": levels,
    }
    store.add_history(entry)
    log.info("ALARMA %s %s %s RSI=%.1f", base, label, action, rsi_now)

    if _in_quiet_hours(cfg.get("schedule", {})):
        return  # registrado en historial pero sin molestar

    title = f"{emoji} {base} · {action}"
    body = f"{label} — RSI {rsi_now:.1f}{mtf_txt}\nEntrada ~{_fmt(price)} USDT"
    if levels:
        body += (f"\n🛑 Stop {_fmt(levels['stop'])}"
                 f"\n🎯 TP {_fmt(levels['tp'])}  (R:R 1:{levels['rr']:g})")
    ch = cfg.get("channels", {})
    if ch.get("telegram"):
        tg = cfg.get("telegram", {})
        await send_telegram_msg(client, tg, f"{title}\n{body}")
    if ch.get("push"):
        push_body = body.replace("\n", " · ")
        await asyncio.to_thread(notify.send_push, title, push_body, symbol)


async def send_telegram_msg(client, tg, text):
    await notify.send_telegram(client, tg.get("token"), tg.get("chat_id"), text)


async def run_monitor():
    store.STATE["assets"] = {}
    async with httpx.AsyncClient() as client:
        while True:
            cfg = store.get_config()
            store.STATE["server_time"] = int(time.time())
            if cfg.get("running"):
                for symbol in store.SYMBOLS:
                    try:
                        await _process_asset(client, symbol, cfg)
                    except Exception as e:  # noqa: BLE001
                        log.error("[%s] ciclo: %s", symbol, e)
            await asyncio.sleep(max(15, int(cfg.get("poll_seconds", 60))))
