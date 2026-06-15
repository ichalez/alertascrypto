"""Estado y persistencia en disco (JSON). Sin base de datos: simple y portable."""
import os
import json
import time
import base64

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
SUBS_PATH = os.path.join(DATA_DIR, "push_subs.json")
VAPID_PRIV_PATH = os.path.join(DATA_DIR, "vapid_private.pem")
VAPID_PUB_PATH = os.path.join(DATA_DIR, "vapid_public.txt")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AAVEUSDT", "AVAXUSDT", "ADAUSDT", "ATOMUSDT"]

# Estado en vivo (en memoria), leído por la API y escrito por el monitor
STATE = {"server_time": 0, "assets": {}}


def _asset_default(oversold, overbought):
    return {
        "enabled": True,
        "oversold": oversold,
        "overbought": overbought,
        "cooldown_seconds": 900,
        "signals": {"simple": True, "turn": True, "exit": True, "divergence": True},
    }


def default_config():
    # SOL/AVAX/AAVE/ATOM son más volátiles -> umbrales algo más amplios por defecto
    wide = {"SOLUSDT", "AVAXUSDT", "AAVEUSDT", "ATOMUSDT"}
    assets = {}
    for s in SYMBOLS:
        assets[s] = _asset_default(25, 75) if s in wide else _asset_default(30, 70)
    return {
        "running": True,
        "poll_seconds": 60,
        "interval": "5m",
        "rsi_period": 14,
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "rr_ratio": 2.0,
        "mtf_filter": True,
        "mtf_interval": "15m",
        "schedule": {"enabled": False, "quiet_start": "00:00", "quiet_end": "07:00"},
        "channels": {"telegram": True, "push": True},
        "telegram": {"token": "", "chat_id": ""},
        "assets": assets,
    }


def _read_json(path, fallback):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _write_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ---- Config ----
_config_cache = None


def get_config():
    global _config_cache
    if _config_cache is None:
        cfg = _read_json(CONFIG_PATH, None)
        if cfg is None:
            cfg = default_config()
            _write_json(CONFIG_PATH, cfg)
        # asegurar que existen todos los activos esperados
        d = default_config()
        for s in SYMBOLS:
            cfg.setdefault("assets", {}).setdefault(s, d["assets"][s])
        _config_cache = cfg
    return _config_cache


def save_config(cfg):
    global _config_cache
    _config_cache = cfg
    _write_json(CONFIG_PATH, cfg)
    return cfg


# ---- Historial ----
def get_history():
    return _read_json(HISTORY_PATH, [])


def add_history(entry):
    hist = get_history()
    hist.insert(0, entry)
    hist = hist[:200]
    _write_json(HISTORY_PATH, hist)
    return hist


def clear_history():
    _write_json(HISTORY_PATH, [])


# ---- Suscripciones push ----
def get_subs():
    return _read_json(SUBS_PATH, [])


def add_sub(sub):
    subs = get_subs()
    endpoints = {s.get("endpoint") for s in subs}
    if sub.get("endpoint") not in endpoints:
        subs.append(sub)
        _write_json(SUBS_PATH, subs)
    return subs


def remove_sub(endpoint):
    subs = [s for s in get_subs() if s.get("endpoint") != endpoint]
    _write_json(SUBS_PATH, subs)
    return subs


# ---- VAPID (claves para Web Push) ----
def ensure_vapid():
    """Genera el par de claves VAPID en el primer arranque y las persiste."""
    if os.path.exists(VAPID_PRIV_PATH) and os.path.exists(VAPID_PUB_PATH):
        return
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    os.makedirs(DATA_DIR, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with open(VAPID_PRIV_PATH, "wb") as f:
        f.write(priv_pem)
    pub_raw = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    with open(VAPID_PUB_PATH, "w") as f:
        f.write(pub_b64)


def vapid_public_key():
    try:
        with open(VAPID_PUB_PATH) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
