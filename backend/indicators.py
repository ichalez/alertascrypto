"""Indicadores técnicos: RSI (Wilder) y divergencias RSI/precio."""


def rsi_series(closes, period=14):
    """Devuelve una lista del RSI alineada con `closes` (None durante el warmup)."""
    n = len(closes)
    out = [None] * n
    if n < period + 1:
        return out

    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [-min(d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def val(ag, al):
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    # deltas[i] corresponde a closes[i+1]; tras consumir `period` deltas el RSI cae en closes[period]
    out[period] = val(avg_gain, avg_loss)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = val(avg_gain, avg_loss)
    return out


def rsi(closes, period=14):
    """RSI del último valor cerrado. None si no hay datos suficientes."""
    s = rsi_series(closes, period)
    return s[-1] if s else None


def atr(highs, lows, closes, period=14):
    """Average True Range (Wilder). Mide la volatilidad media del activo. None si faltan datos."""
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr_val = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
    return atr_val


def _pivot_lows(vals, left=3, right=3):
    idx = []
    for i in range(left, len(vals) - right):
        seg = vals[i - left:i + right + 1]
        if vals[i] == min(seg) and seg.count(min(seg)) == 1:
            idx.append(i)
    return idx


def _pivot_highs(vals, left=3, right=3):
    idx = []
    for i in range(left, len(vals) - right):
        seg = vals[i - left:i + right + 1]
        if vals[i] == max(seg) and seg.count(max(seg)) == 1:
            idx.append(i)
    return idx


def detect_divergence(closes, rsis, recent=6):
    """
    Divergencia simple comparando los dos últimos pivots.
    - alcista: precio hace mínimo más bajo y el RSI mínimo más alto (en zona baja).
    - bajista: precio hace máximo más alto y el RSI máximo más bajo (en zona alta).
    Solo cuenta si el último pivot es reciente (operable ahora). Devuelve 'bullish'/'bearish'/None.
    """
    n = len(closes)
    if n < 20:
        return None

    lows = _pivot_lows(closes)
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        r1, r2 = rsis[i1], rsis[i2]
        if (r1 is not None and r2 is not None
                and closes[i2] < closes[i1]      # mínimo más bajo en precio
                and r2 > r1                       # mínimo más alto en RSI
                and r2 < 45                        # cerca de sobreventa = relevante
                and (n - 1 - i2) <= recent):
            return "bullish"

    highs = _pivot_highs(closes)
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        r1, r2 = rsis[i1], rsis[i2]
        if (r1 is not None and r2 is not None
                and closes[i2] > closes[i1]       # máximo más alto en precio
                and r2 < r1                        # máximo más bajo en RSI
                and r2 > 55                         # cerca de sobrecompra
                and (n - 1 - i2) <= recent):
            return "bearish"

    return None
