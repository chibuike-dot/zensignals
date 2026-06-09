# ============================================================
# Part 1: Imports, Config, Data, Indicators
# ============================================================

import pandas as pd
import numpy as np
import requests
import time
import json
import os
from datetime import datetime, timedelta
import pytz
import urllib.request
import urllib.parse

SUPABASE_URL = "https://bnonwdvjjibxukkicpla.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJub253ZHZqamlieHVra2ljcGxhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA4MzY0MDUsImV4cCI6MjA5NjQxMjQwNX0.VFUCJZGGmBso7GOTNBBcmPqHfR0vdBpLgizbBd4gaGU"

def supabase_insert(data):
    url = f"{SUPABASE_URL}/rest/v1/signals"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Prefer", "return=representation")
    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
            return result[0]["id"] if result else None
    except Exception as e:
        print(f"Supabase insert error: {e}")
        return None

def supabase_get_open_signals():
    url = f"{SUPABASE_URL}/rest/v1/signals?status=eq.OPEN&order=created_at.desc"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"Supabase fetch error: {e}")
        return []

def supabase_update_signal(signal_id, outcome, status):
    url = f"{SUPABASE_URL}/rest/v1/signals?id=eq.{signal_id}"
    body = json.dumps({"outcome": outcome, "status": status, "updated_at": datetime.utcnow().isoformat()}).encode()
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/json")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Supabase update error: {e}")

def supabase_get_recent_signals(limit=10):
    url = f"{SUPABASE_URL}/rest/v1/signals?order=created_at.desc&limit={limit}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"Supabase fetch error: {e}")
        return []

TELEGRAM_TOKEN = "8838997298:AAHLpLhWCjeHcAcNbhlzUThRjvzyc7bXCsc"
CHAT_ID = "6517653689"
SIGNAL_MEMORY_FILE = "signal_memory.json"
COOLDOWN_HOURS = 4
MIN_SCORE = 15
MAX_SCORE = 24

SYMBOLS = [
    ("EURUSD", "FX_IDC", "forex"),
    ("GBPUSD", "FX_IDC", "forex"),
    ("USDJPY", "FX_IDC", "forex"),
    ("AUDUSD", "FX_IDC", "forex"),
    ("USDCAD", "FX_IDC", "forex"),
    ("USDCHF", "FX_IDC", "forex"),
    ("GBPJPY", "FX_IDC", "forex"),
    ("EURJPY", "FX_IDC", "forex"),
    ("EURGBP", "FX_IDC", "forex"),
    ("NZDUSD", "FX_IDC", "forex"),
    ("XAUUSD", "OANDA", "metal"),
    ("XAGUSD", "OANDA", "metal"),
    ("BTCUSD", "COINBASE", "crypto"),
    ("ETHUSD", "COINBASE", "crypto"),
    ("SOLUSD", "COINBASE", "crypto"),
    ("BNBUSD", "BINANCE", "crypto"),
    ("XRPUSD", "COINBASE", "crypto"),
]

TIMEFRAMES = {
    "W":   "in_weekly",
    "D":   "in_daily",
    "4H":  "in_4_hour",
    "1H":  "in_1_hour",
    "15M": "in_15_minute",
    "5M":  "in_5_minute",
}

CRYPTO_FALLBACK = "BINANCE"

KILLZONES = {
    "London":   (7, 10),
    "New York": (12, 15),
}

def get_interval(tf_key):
    from tvDatafeed import Interval
    mapping = {
        "W":   Interval.in_weekly,
        "D":   Interval.in_daily,
        "4H":  Interval.in_4_hour,
        "1H":  Interval.in_1_hour,
        "15M": Interval.in_15_minute,
        "5M":  Interval.in_5_minute,
    }
    return mapping[tf_key]

def get_data(tv, symbol, exchange, tf_key, retries=1):
    import signal as _sig
    def _timeout_handler(s, f): raise TimeoutError("get_hist timeout")
    interval = get_interval(tf_key)
    for i in range(retries):
        try:
            _sig.signal(_sig.SIGALRM, _timeout_handler)
            _sig.alarm(12)
            df = tv.get_hist(symbol, exchange, interval=interval, n_bars=200)
            _sig.alarm(0)
            if df is not None and len(df) > 50:
                df = df.copy()
                df.dropna(inplace=True)
                return df
        except Exception as e:
            print(f"  Retry {i+1} {symbol} {tf_key}: {e}")
            time.sleep(3)
    if exchange == "COINBASE":
        print(f"  Falling back to BINANCE for {symbol}")
        for i in range(retries):
            try:
                df = tv.get_hist(symbol, CRYPTO_FALLBACK, interval=interval, n_bars=200)
                if df is not None and len(df) > 50:
                    df = df.copy()
                    df.dropna(inplace=True)
                    return df
            except:
                time.sleep(3)
    return None

def fetch_all_timeframes(tv, symbol, exchange):
    data = {}
    for tf_key in TIMEFRAMES:
        df = get_data(tv, symbol, exchange, tf_key)
        if df is not None:
            data[tf_key] = df
        time.sleep(1)
    return data

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_stochastic(high, low, close, k_period=14, d_period=3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-10)
    d = k.rolling(d_period).mean()
    return k, d

def calc_adx(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm.abs()) & (minus_dm > 0), 0)
    atr = tr.ewm(com=period-1, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(com=period-1, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(com=period-1, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(com=period-1, min_periods=period).mean()
    return adx

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def get_indicators(df):
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df.get('volume', pd.Series(np.ones(len(df)), index=df.index))
    rsi = calc_rsi(close)
    stoch_k, stoch_d = calc_stochastic(high, low, close)
    adx = calc_adx(high, low, close)
    atr = calc_atr(high, low, close)
    avg_volume = volume.rolling(20).mean()
    return {
        "rsi": round(rsi.iloc[-1], 2),
        "stoch_k": round(stoch_k.iloc[-1], 2),
        "stoch_d": round(stoch_d.iloc[-1], 2),
        "adx": round(adx.iloc[-1], 2),
        "atr": round(atr.iloc[-1], 6),
        "volume": round(volume.iloc[-1], 2),
        "avg_volume": round(avg_volume.iloc[-1], 2),
    }

def is_forex_session():
    ny = pytz.timezone('America/New_York')
    now = datetime.now(ny)
    if now.weekday() >= 5:
        return False
    return True

def get_killzone_session():
    utc_hour = datetime.now(pytz.utc).hour
    for name, (start, end) in KILLZONES.items():
        if start <= utc_hour < end:
            return name
    return None

def is_in_killzone():
    return True  # DEBUG: bypass killzone

def load_memory():
    if os.path.exists(SIGNAL_MEMORY_FILE):
        with open(SIGNAL_MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(SIGNAL_MEMORY_FILE, "w") as f:
        json.dump(memory, f)

def is_on_cooldown(symbol, direction, current_price, memory):
    key = f"{symbol}_{direction}"
    if key not in memory:
        return False
    data = memory[key]
    last_price = data.get("price", 0)
    last_atr = data.get("atr", 0)
    # Price must have moved at least 1x ATR from last signal
    if last_atr > 0 and abs(current_price - last_price) < last_atr:
        return True
    return False

def update_memory(symbol, direction, price, atr, memory):
    key = f"{symbol}_{direction}"
    memory[key] = {
        "price": price,
        "atr": atr,
        "time": datetime.utcnow().isoformat(),
        "entry": price,
    }
    save_memory(memory)

def find_swings(df, lookback=10):
    high = df['high']
    low = df['low']
    swing_highs = []
    swing_lows = []
    for i in range(lookback, len(df) - lookback):
        if high.iloc[i] == high.iloc[i-lookback:i+lookback].max():
            swing_highs.append((i, high.iloc[i]))
        if low.iloc[i] == low.iloc[i-lookback:i+lookback].min():
            swing_lows.append((i, low.iloc[i]))
    return swing_highs, swing_lows

def detect_bos(df):
    close = df['close']
    swing_highs, swing_lows = find_swings(df)
    if not swing_highs or not swing_lows:
        return None
    last_sh = swing_highs[-1][1]
    last_sl = swing_lows[-1][1]
    current_close = close.iloc[-1]
    if current_close > last_sh:
        return "BUY"
    elif current_close < last_sl:
        return "SELL"
    return None

def detect_choch(df):
    close = df['close']
    swing_highs, swing_lows = find_swings(df)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None
    last_sh_val = swing_highs[-1][1]
    prev_sh_val = swing_highs[-2][1]
    last_sl_val = swing_lows[-1][1]
    prev_sl_val = swing_lows[-2][1]
    current_close = close.iloc[-1]
    if last_sh_val < prev_sh_val and current_close > last_sh_val:
        return "BUY"
    if last_sl_val > prev_sl_val and current_close < last_sl_val:
        return "SELL"
    return None

def detect_order_block(df, direction):
    close = df['close']
    open_ = df['open']
    high = df['high']
    low = df['low']
    swing_highs, swing_lows = find_swings(df)
    if not swing_highs or not swing_lows:
        return None
    if direction == "BUY":
        sl_idx = swing_lows[-1][0]
        for i in range(sl_idx, 0, -1):
            if close.iloc[i] < open_.iloc[i]:
                body = abs(close.iloc[i] - open_.iloc[i])
                candle_range = high.iloc[i] - low.iloc[i]
                if candle_range > 0 and body / candle_range > 0.4:
                    return (high.iloc[i], low.iloc[i])
    elif direction == "SELL":
        sh_idx = swing_highs[-1][0]
        for i in range(sh_idx, 0, -1):
            if close.iloc[i] > open_.iloc[i]:
                body = abs(close.iloc[i] - open_.iloc[i])
                candle_range = high.iloc[i] - low.iloc[i]
                if candle_range > 0 and body / candle_range > 0.4:
                    return (high.iloc[i], low.iloc[i])
    return None

def detect_fvg(df, direction):
    high = df['high']
    low = df['low']
    close = df['close']
    for i in range(len(df)-1, 2, -1):
        if direction == "BUY":
            if low.iloc[i] > high.iloc[i-2]:
                fvg_low = high.iloc[i-2]
                fvg_high = low.iloc[i]
                if close.iloc[-1] > fvg_low:
                    return (fvg_high, fvg_low)
        elif direction == "SELL":
            if high.iloc[i] < low.iloc[i-2]:
                fvg_high = low.iloc[i-2]
                fvg_low = high.iloc[i]
                if close.iloc[-1] < fvg_high:
                    return (fvg_high, fvg_low)
    return None

def detect_liquidity_sweep(df, direction):
    high = df['high']
    low = df['low']
    close = df['close']
    swing_highs, swing_lows = find_swings(df)
    if not swing_highs or not swing_lows:
        return False
    if direction == "BUY":
        last_sl = swing_lows[-1][1]
        if low.iloc[-1] < last_sl and close.iloc[-1] > last_sl:
            return True
    elif direction == "SELL":
        last_sh = swing_highs[-1][1]
        if high.iloc[-1] > last_sh and close.iloc[-1] < last_sh:
            return True
    return False

def detect_sfp(df, direction):
    high = df['high']
    low = df['low']
    close = df['close']
    swing_highs, swing_lows = find_swings(df)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return False
    if direction == "BUY":
        prev_sl = swing_lows[-2][1]
        last_sl = swing_lows[-1][1]
        if low.iloc[-1] < prev_sl and close.iloc[-1] > last_sl:
            return True
    elif direction == "SELL":
        prev_sh = swing_highs[-2][1]
        last_sh = swing_highs[-1][1]
        if high.iloc[-1] > prev_sh and close.iloc[-1] < last_sh:
            return True
    return False

def detect_premium_discount(df, direction):
    swing_highs, swing_lows = find_swings(df)
    if not swing_highs or not swing_lows:
        return False
    equilibrium = (swing_highs[-1][1] + swing_lows[-1][1]) / 2
    current_price = df['close'].iloc[-1]
    if direction == "BUY" and current_price < equilibrium:
        return True
    if direction == "SELL" and current_price > equilibrium:
        return True
    return False

def detect_inducement(df, direction):
    swing_highs, swing_lows = find_swings(df, lookback=5)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return False
    current = df['close'].iloc[-1]
    if direction == "BUY":
        if swing_lows[-1][1] < swing_lows[-2][1] and current > swing_lows[-1][1]:
            return True
    elif direction == "SELL":
        if swing_highs[-1][1] > swing_highs[-2][1] and current < swing_highs[-1][1]:
            return True
    return False

def detect_accumulation(df):
    high = df['high']
    low = df['low']
    close = df['close']
    recent_high = high.iloc[-20:].max()
    recent_low = low.iloc[-20:].min()
    range_size = recent_high - recent_low
    atr = calc_atr(high, low, close).iloc[-1]
    if range_size > 2 * atr:
        return False
    sweep_count = sum(1 for i in range(-20, 0) if low.iloc[i] < recent_low)
    return sweep_count >= 2

def detect_distribution(df):
    high = df['high']
    low = df['low']
    close = df['close']
    recent_high = high.iloc[-20:].max()
    recent_low = low.iloc[-20:].min()
    range_size = recent_high - recent_low
    atr = calc_atr(high, low, close).iloc[-1]
    if range_size > 2 * atr:
        return False
    sweep_count = sum(1 for i in range(-20, 0) if high.iloc[i] > recent_high)
    return sweep_count >= 2

def detect_consolidation(df):
    high = df['high']
    low = df['low']
    close = df['close']
    atr = calc_atr(high, low, close)
    recent_atr = atr.iloc[-5:].mean()
    prev_atr = atr.iloc[-20:-5].mean()
    if prev_atr > 0 and recent_atr < prev_atr * 0.6:
        return True
    return False

def detect_retracement(df, direction, ob, fvg):
    current_price = df['close'].iloc[-1]
    if ob:
        ob_high, ob_low = ob
        if ob_low <= current_price <= ob_high:
            return True
    if fvg:
        fvg_high, fvg_low = fvg
        if fvg_low <= current_price <= fvg_high:
            return True
    return False

def get_htf_bias(tf_data):
    biases = []
    for tf in ["W", "D"]:
        if tf not in tf_data:
            continue
        bos = detect_bos(tf_data[tf])
        if bos:
            biases.append(bos)
    if len(biases) == 0:
        return None
    if len(set(biases)) > 1:
        return "CONFLICT"
    return biases[0]

def is_volume_sufficient(indicators):
    vol = indicators.get("volume", 0)
    avg_vol = indicators.get("avg_volume", 1)
    if avg_vol == 0:
        return True
    return vol >= avg_vol * 0.7

def calc_rr(df, direction, ob, atr_val):
    current_price = df['close'].iloc[-1]
    if ob:
        ob_high, ob_low = ob
        sl = ob_low - (atr_val * 0.5) if direction == "BUY" else ob_high + (atr_val * 0.5)
    else:
        sl = current_price - (atr_val * 1.5) if direction == "BUY" else current_price + (atr_val * 1.5)
    entry = current_price
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return None
    tp1 = entry + (sl_distance * 2) if direction == "BUY" else entry - (sl_distance * 2)
    tp2 = entry + (sl_distance * 3) if direction == "BUY" else entry - (sl_distance * 3)
    return {
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "rr": 2.0,
        "sl_distance": round(sl_distance, 6),
    }

def detect_phase(direction, df):
    if df is None:
        return "Unknown"
    if detect_consolidation(df):
        return "Consolidation"
    if direction == "BUY":
        return "Accumulation" if detect_accumulation(df) else "Retracement/Expansion"
    if direction == "SELL":
        return "Distribution" if detect_distribution(df) else "Retracement/Expansion"
    return "Unknown"

def score_symbol(symbol, exchange, asset_type, tf_data, indicators):
    score = 0
    notes = []

    htf_bias = get_htf_bias(tf_data)
    if htf_bias in ("CONFLICT", None):
        print(f"  {symbol}: HTF {htf_bias} — skipping")
        return None

    direction = htf_bias
    score += 3
    notes.append(f"HTF Bias: {direction} ✅ (+3)")

    structure_votes = []
    for tf in ["4H", "1H"]:
        if tf in tf_data:
            if detect_bos(tf_data[tf]) == direction or detect_choch(tf_data[tf]) == direction:
                structure_votes.append(direction)
    if len(structure_votes) == 2:
        score += 2
        notes.append("4H+1H Structure aligned ✅ (+2)")
    elif len(structure_votes) == 1:
        score += 1
        notes.append("Partial structure ✅ (+1)")

    adx = indicators.get("adx", 0)
    if adx >= 25:
        score += 2
        notes.append(f"ADX {adx} strong ✅ (+2)")
    elif adx < 20:
        score -= 2
        notes.append(f"ADX {adx} weak ❌ (-2)")

    ref_tf = "1H" if "1H" in tf_data else "4H"
    if ref_tf in tf_data and detect_consolidation(tf_data[ref_tf]):
        score -= 3
        notes.append("Consolidation ❌ (-3)")

    if score < 0:
        return None

    for tf in ["1H", "15M"]:
        if tf in tf_data and detect_liquidity_sweep(tf_data[tf], direction):
            score += 2
            notes.append(f"Liquidity Sweep {tf} ✅ (+2)")
            break

    for tf in ["1H", "15M"]:
        if tf in tf_data and detect_sfp(tf_data[tf], direction):
            score += 1
            notes.append(f"SFP {tf} ✅ (+1)")
            break

    ob = None
    for tf in ["1H", "4H"]:
        if tf in tf_data:
            ob = detect_order_block(tf_data[tf], direction)
            if ob:
                score += 2
                notes.append(f"Order Block {tf} ✅ (+2)")
                break

    fvg = None
    for tf in ["15M", "1H"]:
        if tf in tf_data:
            fvg = detect_fvg(tf_data[tf], direction)
            if fvg:
                score += 1
                notes.append(f"FVG {tf} ✅ (+1)")
                break

    ref_df = tf_data.get("15M") if tf_data.get("15M") is not None else tf_data.get("1H")
    if ref_df is not None:
        if detect_retracement(ref_df, direction, ob, fvg):
            score += 2
            notes.append("Retracement into OB/FVG ✅ (+2)")
        if direction == "BUY" and detect_accumulation(ref_df):
            score += 2
            notes.append("Accumulation ✅ (+2)")
        elif direction == "SELL" and detect_distribution(ref_df):
            score += 2
            notes.append("Distribution ✅ (+2)")
        if detect_premium_discount(ref_df, direction):
            score += 1
            notes.append("Premium/Discount ✅ (+1)")
        if detect_inducement(ref_df, direction):
            score += 1
            notes.append("Inducement ✅ (+1)")

    rsi = indicators.get("rsi", 50)
    if direction == "BUY" and rsi < 40:
        score += 1
        notes.append(f"RSI {rsi} oversold ✅ (+1)")
    elif direction == "SELL" and rsi > 60:
        score += 1
        notes.append(f"RSI {rsi} overbought ✅ (+1)")

    stoch_k = indicators.get("stoch_k", 50)
    if direction == "BUY" and stoch_k < 25:
        score += 1
        notes.append(f"Stoch {stoch_k} oversold ✅ (+1)")
    elif direction == "SELL" and stoch_k > 75:
        score += 1
        notes.append(f"Stoch {stoch_k} overbought ✅ (+1)")

    session = get_killzone_session()
    if session:
        score += 1
        notes.append(f"Killzone: {session} ✅ (+1)")

    if not is_volume_sufficient(indicators):
        score -= 1
        notes.append("Low volume ❌ (-1)")

    atr_val = indicators.get("atr", 0.001)
    rr_data = calc_rr(ref_df, direction, ob, atr_val) if ref_df is not None else None
    if rr_data is None:
        return None
    score += 2
    notes.append(f"RR {rr_data['rr']}:1 ✅ (+2)")

    print(f"  {symbol}: score={score}/24 direction={direction}")
    for n in notes:
        print(f"    {n}")

    if score < MIN_SCORE:
        print(f"  {symbol}: Below threshold — no signal")
        return None

    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "notes": notes,
        "rr_data": rr_data,
        "indicators": indicators,
        "session": session or "Off-session",
        "phase": detect_phase(direction, ref_df),
    }

def format_signal(result):
    direction = result['direction']
    emoji = "🟢" if direction == "BUY" else "🔴"
    arrow = "⬆️" if direction == "BUY" else "⬇️"
    rr = result['rr_data']
    ind = result['indicators']
    now_str = datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d %H:%M')
    return (
        f"{emoji} <b>ZenSignals Pro Alert</b> {arrow}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Pair: <b>{result['symbol']}</b>\n"
        f"📍 Signal: <b>{direction}</b>\n"
        f"📊 Score: <b>{result['score']}/24</b>\n"
        f"🔄 Phase: <b>{result['phase']}</b>\n"
        f"⏰ Session: <b>{result['session']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Entry: <b>{rr['entry']}</b>\n"
        f"🛑 SL: <b>{rr['sl']}</b>\n"
        f"🎯 TP1 (1:2): <b>{rr['tp1']}</b>\n"
        f"🏆 TP2 (1:3): <b>{rr['tp2']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 RSI: <b>{ind['rsi']}</b>\n"
        f"📉 Stoch: <b>{ind['stoch_k']}</b>\n"
        f"💪 ADX: <b>{ind['adx']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 Time: <b>{now_str} NY</b>\n"
        f"⚠️ <i>Always confirm before entering</i>"
    )

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def run_scan(tv):
    print(f"\n{'='*50}")
    print(f"ZenSignals Pro — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}")
    memory = load_memory()
    signals_found = 0
    for symbol, exchange, asset_type in SYMBOLS:
        print(f"\n🔍 Scanning {symbol}...")
        if asset_type == "forex" and not is_forex_session():
            print(f"  Skipping — forex market closed")
            continue
        tf_data = fetch_all_timeframes(tv, symbol, exchange)
        if len(tf_data) < 2:
            print(f"  Insufficient data")
            continue
        ref_tf = "1H" if "1H" in tf_data else list(tf_data.keys())[0]
        indicators = get_indicators(tf_data[ref_tf])
        result = score_symbol(symbol, exchange, asset_type, tf_data, indicators)
        if result is None:
            continue
        current_price = result['rr_data']['entry']
        current_atr = result['indicators']['atr']
        if is_on_cooldown(symbol, result['direction'], current_price, memory):
            print(f"  Price hasn\'t moved enough — skipping")
            continue
        msg = format_signal(result)
        send_telegram(msg)
        update_memory(symbol, result['direction'], result['rr_data']['entry'], result['indicators']['atr'], memory)
        # Save to Supabase
        supabase_insert({
            "symbol": symbol,
            "direction": result['direction'],
            "score": result['score'],
            "phase": result['phase'],
            "session": result['session'],
            "entry": result['rr_data']['entry'],
            "sl": result['rr_data']['sl'],
            "tp1": result['rr_data']['tp1'],
            "tp2": result['rr_data']['tp2'],
            "rsi": result['indicators']['rsi'],
            "stoch": result['indicators']['stoch_k'],
            "adx": result['indicators']['adx'],
            "atr": result['indicators']['atr'],
            "status": "OPEN",
        })
        print(f"  ✅ Signal sent: {result['direction']} {symbol} {result['score']}/24")
        signals_found += 1
        time.sleep(2)
    print(f"\nScan complete — {signals_found} signal(s) sent")

    


def send_signal_updates(memory):
    """
    Option 4: Hourly P&L update for all open signals
    Only runs if there are active signals in memory
    """
    if not memory:
        return

    now = datetime.utcnow()
    updates = []

    for key, data in memory.items():
        if not isinstance(data, dict):
            continue

        symbol_dir = key.split("_")
        if len(symbol_dir) < 2:
            continue

        direction = symbol_dir[-1]
        symbol = "_".join(symbol_dir[:-1])
        entry = data.get("entry", 0)
        signal_time = data.get("time", "")
        atr = data.get("atr", 0)

        if not entry or not signal_time:
            continue

        # Only show updates for signals less than 24 hours old
        try:
            signal_dt = datetime.fromisoformat(signal_time)
            age_hours = (now - signal_dt).total_seconds() / 3600
            if age_hours > 24:
                continue
        except:
            continue

        # Calculate TP1 and SL from entry and ATR
        sl_dist = atr * 1.5
        if direction == "BUY":
            sl = entry - sl_dist
            tp1 = entry + (sl_dist * 2)
        else:
            sl = entry + sl_dist
            tp1 = entry - (sl_dist * 2)

        emoji = "🟢" if direction == "BUY" else "🔴"
        age_str = f"{age_hours:.1f}h ago"

        updates.append(
            f"{emoji} <b>{symbol}</b> {direction}\n"
            f"   Entry: {round(entry, 5)}\n"
            f"   TP1: {round(tp1, 5)}\n"
            f"   SL: {round(sl, 5)}\n"
            f"   Signalled: {age_str}"
        )

    if not updates:
        return

    ny = pytz.timezone('America/New_York')
    now_str = datetime.now(ny).strftime('%Y-%m-%d %H:%M')

    msg = (
        f"📊 <b>ZenSignals Pro — Signal Status</b>\n"
        f"🕐 {now_str} NY\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        + "\n━━━━━━━━━━━━━━━━━━\n".join(updates) +
        f"\n━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Confirm live prices before acting</i>"
    )
    send_telegram(msg)
    print("Signal status update sent to Telegram")

def check_outcomes(tv):
    """
    Check all open signals against current price
    Mark as WIN/LOSS if TP1 or SL hit
    """
    open_signals = supabase_get_open_signals()
    if not open_signals:
        return

    print(f"\nChecking outcomes for {len(open_signals)} open signal(s)...")

    for sig in open_signals:
        symbol = sig['symbol']
        direction = sig['direction']
        entry = float(sig['entry'])
        tp1 = float(sig['tp1'])
        tp2 = float(sig['tp2'])
        sl = float(sig['sl'])
        sig_id = sig['id']

        # Get current price
        exchange = next(
            (e for s, e, t in SYMBOLS if s == symbol),
            "FX_IDC"
        )
        df = get_data(tv, symbol, exchange, "5M")
        if df is None:
            continue

        current = df['close'].iloc[-1]
        outcome = None
        status = None

        if direction == "BUY":
            if current >= tp2:
                outcome = "TP2_HIT"
                status = "CLOSED"
            elif current >= tp1:
                outcome = "TP1_HIT"
                status = "CLOSED"
            elif current <= sl:
                outcome = "SL_HIT"
                status = "CLOSED"
        else:
            if current <= tp2:
                outcome = "TP2_HIT"
                status = "CLOSED"
            elif current <= tp1:
                outcome = "TP1_HIT"
                status = "CLOSED"
            elif current >= sl:
                outcome = "SL_HIT"
                status = "CLOSED"

        if outcome:
            supabase_update_signal(sig_id, outcome, status)
            emoji = "🏆" if "TP" in outcome else "❌"
            msg = (
                f"{emoji} <b>ZenSignals Outcome</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 Pair: <b>{symbol}</b>\n"
                f"📍 Direction: <b>{direction}</b>\n"
                f"📊 Result: <b>{outcome}</b>\n"
                f"💰 Entry: {entry}\n"
                f"📍 Current: {round(current, 5)}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🕐 {datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d %H:%M')} NY"
            )
            send_telegram(msg)
            print(f"  {outcome}: {symbol} {direction}")

def check_invalidation(sig, df_1h, df_4h, current_price):
    """
    Checks 6 invalidation conditions for an open signal.
    Returns (True, reason) if invalidated, (False, None) if still valid.
    """
    direction = sig['direction']
    entry = float(sig['entry'])
    sl = float(sig['sl'])
    tp1 = float(sig['tp1'])
    atr = float(sig['atr']) if sig.get('atr') else 0.001
    created_at = sig.get('created_at', '')
    asset_type = 'crypto' if any(
        sig['symbol'] == s for s, e, t in SYMBOLS if t == 'crypto'
    ) else 'forex'

    # ── 1. SL BREACHED BEFORE ENTRY ─────────────────────
    if direction == "BUY" and current_price <= sl:
        return True, "SL level breached before entry"
    if direction == "SELL" and current_price >= sl:
        return True, "SL level breached before entry"

    # ── 2. TIME EXPIRY ───────────────────────────────────
    try:
        signal_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        signal_time = signal_time.replace(tzinfo=None)
        elapsed = (datetime.utcnow() - signal_time).total_seconds() / 3600
        expiry = 2 if asset_type == 'crypto' else 4
        if elapsed > expiry:
            return True, f"Signal expired after {expiry} hours"
    except:
        pass

    # ── 3. OPPOSING BOS ON 1H ────────────────────────────
    if df_1h is not None:
        swing_highs, swing_lows = find_swings(df_1h)
        if swing_highs and swing_lows:
            if direction == "SELL":
                last_sh = swing_highs[-1][1]
                if current_price > last_sh:
                    return True, f"Opposing BOS — price broke above {round(last_sh, 5)}"
            if direction == "BUY":
                last_sl = swing_lows[-1][1]
                if current_price < last_sl:
                    return True, f"Opposing BOS — price broke below {round(last_sl, 5)}"

    # ── 4. ORDER BLOCK MITIGATED ─────────────────────────
    if df_1h is not None:
        ob = detect_order_block(df_1h, direction)
        if ob:
            ob_high, ob_low = ob
            if direction == "BUY":
                # Price closed full candle body below OB
                if df_1h['close'].iloc[-1] < ob_low and df_1h['open'].iloc[-1] < ob_low:
                    return True, f"Order Block mitigated — closed below {round(ob_low, 5)}"
            if direction == "SELL":
                # Price closed full candle body above OB
                if df_1h['close'].iloc[-1] > ob_high and df_1h['open'].iloc[-1] > ob_high:
                    return True, f"Order Block mitigated — closed above {round(ob_high, 5)}"

    # ── 5. FVG FULLY FILLED ──────────────────────────────
    if df_1h is not None:
        fvg = detect_fvg(df_1h, direction)
        if fvg is None:
            # FVG no longer detectable = fully filled
            pass  # Only invalidate if we can confirm it was filled
        if fvg:
            fvg_high, fvg_low = fvg
            if direction == "BUY" and current_price < fvg_low:
                return True, f"FVG fully filled — price below {round(fvg_low, 5)}"
            if direction == "SELL" and current_price > fvg_high:
                return True, f"FVG fully filled — price above {round(fvg_high, 5)}"

    # ── 6. 4H BIAS FLIP ──────────────────────────────────
    if df_4h is not None:
        bias_4h = detect_bos(df_4h)
        if bias_4h and bias_4h != direction:
            return True, f"4H bias flipped to {bias_4h}"

    return False, None

# ============================================================
# PART 1: VOLATILITY + SWING SEQUENCE ENGINE
# ============================================================

def get_volatility_state(df):
    """
    Measures raw volatility using ATR vs 20-period average
    Returns: state, atr_ratio, conviction
    """
    high = df['high']
    low = df['low']
    close = df['close']
    open_ = df['open']

    atr = calc_atr(high, low, close)
    current_atr = atr.iloc[-1]
    avg_atr = atr.iloc[-20:].mean()
    atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

    # Conviction = body size vs total range
    last_body = abs(close.iloc[-1] - open_.iloc[-1])
    last_range = high.iloc[-1] - low.iloc[-1]
    conviction = round(last_body / last_range * 100, 1) if last_range > 0 else 50.0

    # Check last 3 candles for alternating direction
    directions = []
    for i in range(-4, 0):
        if close.iloc[i] > open_.iloc[i]:
            directions.append("UP")
        else:
            directions.append("DOWN")

    alternating = all(
        directions[i] != directions[i+1]
        for i in range(len(directions)-1)
    )

    # Single candle spike check
    spike = atr_ratio > 2.5

    if spike:
        state = "SPIKE"
    elif alternating:
        state = "INDECISION"
    elif atr_ratio > 1.5:
        state = "HIGH"
    elif atr_ratio < 0.75:
        state = "LOW"
    else:
        state = "NORMAL"

    return {
        "state": state,
        "atr_ratio": round(atr_ratio, 2),
        "conviction": conviction,
        "spike": spike,
        "alternating": alternating,
    }


def analyze_swing_sequence(df):
    """
    Detects HH/HL/LH/LL swing sequence
    Returns trend type and confidence
    """
    swing_highs, swing_lows = find_swings(df, lookback=5)

    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return {
            "sequence": "UNKNOWN",
            "trend": "UNKNOWN",
            "confidence": "LOW",
            "description": "Insufficient swing data",
        }

    # Last 3 highs and lows
    h1, h2, h3 = swing_highs[-3][1], swing_highs[-2][1], swing_highs[-1][1]
    l1, l2, l3 = swing_lows[-3][1], swing_lows[-2][1], swing_lows[-1][1]

    # Classify highs
    hh = h3 > h2 > h1  # Higher Highs
    lh = h3 < h2       # Lower High (latest)
    # Classify lows
    hl = l3 > l2 > l1  # Higher Lows
    ll = l3 < l2       # Lower Low (latest)

    # Determine sequence
    if hh and hl:
        sequence = "HH+HL"
        trend = "BULLISH_TREND"
        confidence = "HIGH"
        description = "Strong bullish — higher highs and higher lows"
    elif ll and lh:
        sequence = "LH+LL"
        trend = "BEARISH_TREND"
        confidence = "HIGH"
        description = "Strong bearish — lower highs and lower lows"
    elif hh and ll:
        sequence = "HH+LL"
        trend = "CHOPPY_EXPANDING"
        confidence = "LOW"
        description = "Expanding range — no directional commitment"
    elif lh and hl:
        sequence = "LH+HL"
        trend = "CHOPPY_CONTRACTING"
        confidence = "LOW"
        description = "Contracting range — compression before breakout"
    elif hh and not hl:
        sequence = "HH+FL"
        trend = "WEAKENING_BULL"
        confidence = "MEDIUM"
        description = "Bullish weakening — highs rising but lows flat"
    elif ll and not lh:
        sequence = "FL+LL"
        trend = "WEAKENING_BEAR"
        confidence = "MEDIUM"
        description = "Bearish weakening — lows falling but highs flat"
    elif lh and not ll:
        sequence = "LH+FL"
        trend = "REVERSAL_FORMING"
        confidence = "MEDIUM"
        description = "Potential reversal — lower high forming"
    else:
        sequence = "MIXED"
        trend = "TRANSITIONAL"
        confidence = "LOW"
        description = "Mixed structure — market transitioning"

    return {
        "sequence": sequence,
        "trend": trend,
        "confidence": confidence,
        "description": description,
        "highs": [round(h1,5), round(h2,5), round(h3,5)],
        "lows": [round(l1,5), round(l2,5), round(l3,5)],
    }


def get_momentum_state(df, indicators):
    """
    Combines ATR, RSI direction, candle conviction
    Returns momentum state and score
    """
    rsi = indicators.get("rsi", 50)
    stoch = indicators.get("stoch_k", 50)
    adx = indicators.get("adx", 20)
    vol = get_volatility_state(df)

    score = 0

    # ATR component
    if vol["atr_ratio"] > 1.5:
        score += 3
    elif vol["atr_ratio"] > 1.0:
        score += 2
    else:
        score += 1

    # ADX component
    if adx > 40:
        score += 3
    elif adx > 25:
        score += 2
    else:
        score += 1

    # RSI momentum
    rsi_prev = indicators.get("rsi", 50)
    if rsi > 60 or rsi < 40:
        score += 2
    else:
        score += 1

    # Conviction
    if vol["conviction"] > 65:
        score += 2
    elif vol["conviction"] > 45:
        score += 1

    # Determine state
    if score >= 9:
        state = "VERY_HIGH"
    elif score >= 7:
        state = "HIGH"
    elif score >= 5:
        state = "MEDIUM"
    else:
        state = "LOW"

    return {
        "state": state,
        "score": score,
        "atr_ratio": vol["atr_ratio"],
        "conviction": vol["conviction"],
        "adx": adx,
    }

# ============================================================
# PART 2: THREE TIMEFRAME MODEL + DURATION CALCULATOR
# ============================================================

def get_ctf_itf_ttf(tf_data, direction):
    """
    Determines CTF, ITF, TTF based on where
    the strongest signal conditions were found
    """
    # Timeframe hierarchy
    tf_hierarchy = ["W", "D", "4H", "1H", "15M", "5M"]
    tf_labels = {
        "W": "Weekly", "D": "Daily", "4H": "4 Hour",
        "1H": "1 Hour", "15M": "15 Min", "5M": "5 Min"
    }

    # Find CTF — highest TF with confirmed BOS
    ctf = None
    for tf in tf_hierarchy:
        if tf in tf_data:
            bos = detect_bos(tf_data[tf])
            if bos == direction:
                ctf = tf
                break

    if ctf is None:
        ctf = "4H"

    # ITF = one level below CTF
    ctf_idx = tf_hierarchy.index(ctf)
    itf_idx = min(ctf_idx + 1, len(tf_hierarchy) - 1)
    itf = tf_hierarchy[itf_idx]

    # TTF = two levels below CTF
    ttf_idx = min(ctf_idx + 2, len(tf_hierarchy) - 1)
    ttf = tf_hierarchy[ttf_idx]

    # Check ITF confirmation
    itf_confirmed = False
    if itf in tf_data:
        choch = detect_choch(tf_data[itf])
        fvg = detect_fvg(tf_data[itf], direction)
        itf_confirmed = (choch == direction) or (fvg is not None)

    # Check TTF trigger
    ttf_triggered = False
    if ttf in tf_data:
        ob = detect_order_block(tf_data[ttf], direction)
        bos = detect_bos(tf_data[ttf])
        ttf_triggered = (ob is not None) or (bos == direction)

    return {
        "ctf": ctf,
        "itf": itf,
        "ttf": ttf,
        "ctf_label": tf_labels.get(ctf, ctf),
        "itf_label": tf_labels.get(itf, itf),
        "ttf_label": tf_labels.get(ttf, ttf),
        "itf_confirmed": itf_confirmed,
        "ttf_triggered": ttf_triggered,
    }


def get_trade_type(ctf):
    """
    Maps CTF to trade type and base duration
    """
    mapping = {
        "W":   ("Position",       "1-4 weeks",   672),
        "D":   ("Swing",          "3-7 days",    168),
        "4H":  ("Intraday",       "4-12 hours",   8),
        "1H":  ("Intraday Scalp", "1-4 hours",    3),
        "15M": ("Scalp",          "15-60 mins",   1),
        "5M":  ("Micro Scalp",    "5-20 mins",  0.3),
    }
    return mapping.get(ctf, ("Intraday", "4-12 hours", 8))


def calculate_duration(
    ctf, tf_data, direction,
    volatility, swing_seq, momentum,
    itf_confirmed, ttf_triggered,
    asset_type
):
    """
    Calculates dynamic trade duration based on:
    - CTF base duration
    - Volatility state
    - Swing sequence
    - Momentum
    - ITF/TTF confirmation
    - Asset type
    """
    trade_type, duration_label, base_hours = get_trade_type(ctf)
    adjustment_log = []
    hours = base_hours

    # ITF confirmation discount
    if itf_confirmed:
        hours *= 0.80
        adjustment_log.append("ITF confirmed: -20%")

    # TTF trigger discount
    if ttf_triggered:
        hours *= 0.85
        adjustment_log.append("TTF triggered: -15%")

    # Volatility adjustment
    vol_state = volatility.get("state", "NORMAL")
    if vol_state == "HIGH":
        hours *= 0.70
        adjustment_log.append("High volatility: -30%")
    elif vol_state == "LOW":
        hours *= 1.50
        adjustment_log.append("Low volatility: +50%")
    elif vol_state == "SPIKE":
        hours *= 1.20
        adjustment_log.append("Spike detected: +20% (wait for settle)")
    elif vol_state == "INDECISION":
        hours *= 1.80
        adjustment_log.append("Indecision candles: +80%")

    # Swing sequence adjustment
    trend = swing_seq.get("trend", "UNKNOWN")
    if trend in ("BULLISH_TREND", "BEARISH_TREND"):
        hours *= 0.80
        adjustment_log.append("Clean trend: -20%")
    elif trend in ("WEAKENING_BULL", "WEAKENING_BEAR"):
        hours *= 1.30
        adjustment_log.append("Weakening trend: +30%")
    elif trend in ("CHOPPY_EXPANDING", "CHOPPY_CONTRACTING"):
        hours *= 1.80
        adjustment_log.append("Choppy market: +80%")
    elif trend == "REVERSAL_FORMING":
        hours *= 1.40
        adjustment_log.append("Reversal forming: +40%")

    # Momentum adjustment
    mom_state = momentum.get("state", "MEDIUM")
    if mom_state == "VERY_HIGH":
        hours *= 0.65
        adjustment_log.append("Very high momentum: -35%")
    elif mom_state == "HIGH":
        hours *= 0.80
        adjustment_log.append("High momentum: -20%")
    elif mom_state == "LOW":
        hours *= 1.40
        adjustment_log.append("Low momentum: +40%")

    # Crypto runs 24/7 — no session deadline
    # Forex capped at session length
    if asset_type == "forex":
        # Cap at 8 hours for intraday forex
        if ctf in ("1H", "15M", "5M") and hours > 8:
            hours = 8
            adjustment_log.append("Forex session cap: 8h max")

    hours = round(hours, 1)

    # Calculate exact end time
    now_utc = datetime.utcnow()
    end_time = now_utc + timedelta(hours=hours)
    ny = pytz.timezone('America/New_York')
    end_time_ny = end_time.replace(tzinfo=pytz.utc).astimezone(ny)
    start_time_ny = now_utc.replace(tzinfo=pytz.utc).astimezone(ny)

    return {
        "trade_type": trade_type,
        "duration_label": duration_label,
        "base_hours": base_hours,
        "adjusted_hours": hours,
        "adjustment_log": " | ".join(adjustment_log),
        "start_time": start_time_ny.strftime("%d %b %H:%M NY"),
        "end_time": end_time_ny.strftime("%d %b %H:%M NY"),
        "end_time_iso": end_time.isoformat(),
        "ctf": ctf,
    }


def get_live_progress(sig, current_price):
    """
    Calculates live progress of an open trade
    """
    direction = sig['direction']
    entry = float(sig['entry'])
    tp1 = float(sig['tp1'])
    sl = float(sig['sl'])

    total_distance = abs(tp1 - entry)
    if total_distance == 0:
        return 0

    if direction == "BUY":
        progress = (current_price - entry) / total_distance * 100
    else:
        progress = (entry - current_price) / total_distance * 100

    return round(max(0, min(100, progress)), 1)


def get_revised_end_time(sig, momentum_state, volatility_state):
    """
    Revises end time based on current momentum and volatility
    """
    try:
        end_str = sig.get('estimated_end_time', '')
        if not end_str:
            # Estimate from created_at + 8 hours default
            created = sig.get('created_at', '')
            if not created:
                return "Not available"
            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00')).replace(tzinfo=None)
            original_end = created_dt + timedelta(hours=8)
        else:
            original_end = datetime.fromisoformat(end_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except:
        return "Not available"

    remaining = (original_end - datetime.utcnow()).total_seconds() / 3600
    if remaining <= 0:
        return "Elapsed"

    # Adjust remaining based on current momentum
    if momentum_state == "VERY_HIGH":
        remaining *= 0.60
    elif momentum_state == "HIGH":
        remaining *= 0.75
    elif momentum_state == "LOW":
        remaining *= 1.30

    # Adjust for volatility
    if volatility_state == "HIGH":
        remaining *= 0.80
    elif volatility_state == "LOW":
        remaining *= 1.20

    new_end = datetime.utcnow() + timedelta(hours=remaining)
    ny = pytz.timezone('America/New_York')
    new_end_ny = new_end.replace(tzinfo=pytz.utc).astimezone(ny)
    return new_end_ny.strftime("%d %b %H:%M NY")

# ============================================================
# PART 3: NEWS INTEGRATION (ForexFactory)
# ============================================================

def fetch_news_calendar():
    """
    Fetches high/medium impact news from ForexFactory
    Returns list of upcoming news events
    """
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return data
    except Exception as e:
        print(f"News fetch error: {e}")
        return []


def get_relevant_news(symbol, hours_ahead=4):
    """
    Gets news relevant to a symbol within next N hours
    Maps currency pairs to their currencies
    """
    currency_map = {
        "EURUSD": ["EUR", "USD"],
        "GBPUSD": ["GBP", "USD"],
        "USDJPY": ["USD", "JPY"],
        "AUDUSD": ["AUD", "USD"],
        "USDCAD": ["USD", "CAD"],
        "USDCHF": ["USD", "CHF"],
        "GBPJPY": ["GBP", "JPY"],
        "EURJPY": ["EUR", "JPY"],
        "EURGBP": ["EUR", "GBP"],
        "NZDUSD": ["NZD", "USD"],
        "XAUUSD": ["USD"],
        "XAGUSD": ["USD"],
        "BTCUSD": [],
        "ETHUSD": [],
        "SOLUSD": [],
        "BNBUSD": [],
        "XRPUSD": [],
    }

    currencies = currency_map.get(symbol, [])
    if not currencies:
        return []

    news = fetch_news_calendar()
    now_utc = datetime.utcnow()
    cutoff = now_utc + timedelta(hours=hours_ahead)
    relevant = []

    for event in news:
        try:
            # Parse event time
            event_time = datetime.strptime(
                event.get("date", "") + " " + event.get("time", "12:00am"),
                "%m-%d-%Y %I:%M%p"
            )
        except:
            continue

        # Check if within window
        if not (now_utc <= event_time <= cutoff):
            continue

        # Check if relevant currency
        event_currency = event.get("country", "").upper()
        if event_currency not in currencies:
            continue

        # Check impact
        impact = event.get("impact", "").lower()
        if impact not in ("high", "medium"):
            continue

        # Minutes until event
        mins_until = (event_time - now_utc).total_seconds() / 60

        relevant.append({
            "title": event.get("title", "Unknown"),
            "currency": event_currency,
            "impact": impact.upper(),
            "time": event_time.strftime("%H:%M UTC"),
            "mins_until": round(mins_until),
        })

    return relevant


def assess_news_impact(symbol, direction, news_events):
    """
    Assesses how upcoming news affects signal validity
    Returns action recommendation
    """
    if not news_events:
        return {
            "status": "CLEAR",
            "message": "No high impact news in window ✅",
            "suspend": False,
            "action": None,
        }

    high_impact = [n for n in news_events if n["impact"] == "HIGH"]
    medium_impact = [n for n in news_events if n["impact"] == "MEDIUM"]

    # Check if any event is within 30 minutes
    imminent = [n for n in high_impact if n["mins_until"] <= 30]

    if imminent:
        event = imminent[0]
        return {
            "status": "SUSPEND",
            "message": f"⚠️ {event['title']} in {event['mins_until']} mins",
            "suspend": True,
            "action": "Do NOT enter — wait 15 mins after news",
            "event": event,
        }

    if high_impact:
        event = high_impact[0]
        return {
            "status": "CAUTION",
            "message": f"📰 {event['title']} in {event['mins_until']} mins",
            "suspend": False,
            "action": "Move SL to breakeven before news",
            "event": event,
        }

    if medium_impact:
        event = medium_impact[0]
        return {
            "status": "MONITOR",
            "message": f"📋 {event['title']} in {event['mins_until']} mins",
            "suspend": False,
            "action": "Monitor — medium impact event approaching",
            "event": event,
        }

    return {
        "status": "CLEAR",
        "message": "No significant news in window ✅",
        "suspend": False,
        "action": None,
    }

# ============================================================
# PART 4: ENHANCED SIGNAL FORMATTER + LIVE UPDATES
# ============================================================

def format_signal_enhanced(result, tf_model, duration, volatility,
                            swing_seq, momentum, news):
    """
    Full enhanced signal message with all analysis
    """
    direction = result['direction']
    emoji = "🟢" if direction == "BUY" else "🔴"
    arrow = "⬆️" if direction == "BUY" else "⬇️"
    rr = result['rr_data']
    ind = result['indicators']

    # Trade type emoji
    type_emoji = {
        "Micro Scalp": "⚡",
        "Scalp": "⚡",
        "Intraday Scalp": "🎯",
        "Intraday": "📊",
        "Swing": "🌊",
        "Position": "🏦",
    }.get(duration['trade_type'], "📊")

    # Volatility emoji
    vol_emoji = {
        "HIGH": "🔥",
        "NORMAL": "✅",
        "LOW": "🐢",
        "SPIKE": "🚨",
        "INDECISION": "⚠️",
    }.get(volatility['state'], "✅")

    # Momentum emoji
    mom_emoji = {
        "VERY_HIGH": "🚀",
        "HIGH": "⚡",
        "MEDIUM": "📈",
        "LOW": "🐌",
    }.get(momentum['state'], "📈")

    # Swing sequence emoji
    swing_emoji = {
        "BULLISH_TREND": "📈",
        "BEARISH_TREND": "📉",
        "CHOPPY_EXPANDING": "⚠️",
        "CHOPPY_CONTRACTING": "🔄",
        "WEAKENING_BULL": "⚠️",
        "WEAKENING_BEAR": "⚠️",
        "REVERSAL_FORMING": "🔄",
    }.get(swing_seq['trend'], "📊")

    # News status
    news_line = news.get('message', 'No news data')
    news_action = news.get('action', '')

    # ITF/TTF status
    itf_status = "✅" if tf_model['itf_confirmed'] else "⏳"
    ttf_status = "✅" if tf_model['ttf_triggered'] else "⏳"

    msg = (
        f"{emoji} <b>ZenSignals Pro Alert</b> {arrow}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Pair: <b>{result['symbol']}</b>\n"
        f"📍 Signal: <b>{direction}</b>\n"
        f"📊 Score: <b>{result['score']}/24</b>\n"
        f"🔄 Phase: <b>{result['phase']}</b>\n"
        f"⏰ Session: <b>{result['session']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{type_emoji} Trade Type: <b>{duration['trade_type']}</b>\n"
        f"🟢 Start: <b>{duration['start_time']}</b>\n"
        f"🔴 Est. End: <b>{duration['end_time']}</b>\n"
        f"⏳ Duration: <b>~{duration['adjusted_hours']}h</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 TIMEFRAME MODEL\n"
        f"🔵 CTF ({tf_model['ctf_label']}): Bias confirmed\n"
        f"🟡 ITF ({tf_model['itf_label']}): {itf_status}\n"
        f"🟢 TTF ({tf_model['ttf_label']}): {ttf_status}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 MARKET STRUCTURE\n"
        f"{swing_emoji} Sequence: <b>{swing_seq['sequence']}</b>\n"
        f"📊 Trend: <b>{swing_seq['trend']}</b>\n"
        f"{vol_emoji} Volatility: <b>{volatility['state']}</b> "
        f"(ATR {volatility['atr_ratio']}×)\n"
        f"🕯 Conviction: <b>{volatility['conviction']}%</b>\n"
        f"{mom_emoji} Momentum: <b>{momentum['state']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Entry: <b>{rr['entry']}</b>\n"
        f"🛑 SL: <b>{rr['sl']}</b>\n"
        f"🎯 TP1 (1:2): <b>{rr['tp1']}</b>\n"
        f"🏆 TP2 (1:3): <b>{rr['tp2']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 RSI: <b>{ind['rsi']}</b>\n"
        f"📉 Stoch: <b>{ind['stoch_k']}</b>\n"
        f"💪 ADX: <b>{ind['adx']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📰 NEWS: {news_line}\n"
    )

    if news_action:
        msg += f"⚡ Action: <i>{news_action}</i>\n"

    msg += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 Time: <b>{duration['start_time']}</b>\n"
        f"⚠️ <i>Always confirm before entering</i>"
    )

    return msg


def send_live_update(sig, tv):
    """
    Sends live update for an open signal
    """
    symbol = sig['symbol']
    direction = sig['direction']
    exchange = next(
        (e for s, e, t in SYMBOLS if s == symbol),
        "FX_IDC"
    )

    # Get current data
    df_ref = get_data(tv, symbol, exchange, "15M")
    if df_ref is None:
        df_ref = get_data(tv, symbol, exchange, "1H")
    if df_ref is None:
        return

    current_price = df_ref['close'].iloc[-1]
    indicators = get_indicators(df_ref)
    volatility = get_volatility_state(df_ref)
    swing_seq = analyze_swing_sequence(df_ref)
    momentum = get_momentum_state(df_ref, indicators)

    progress = get_live_progress(sig, current_price)
    revised_end = get_revised_end_time(
        sig, momentum['state'], volatility['state']
    )

    # Calculate elapsed time
    try:
        created = datetime.fromisoformat(
            sig.get('created_at', '').replace('Z', '+00:00')
        ).replace(tzinfo=None)
        elapsed_mins = int((datetime.utcnow() - created).total_seconds() / 60)
        elapsed_str = f"{elapsed_mins // 60}h {elapsed_mins % 60}m"
    except:
        elapsed_str = "Unknown"

    emoji = "🟢" if direction == "BUY" else "🔴"
    vol_emoji = {"HIGH": "🔥", "NORMAL": "✅",
                 "LOW": "🐢", "SPIKE": "🚨",
                 "INDECISION": "⚠️"}.get(volatility['state'], "✅")
    mom_emoji = {"VERY_HIGH": "🚀", "HIGH": "⚡",
                 "MEDIUM": "📈", "LOW": "🐌"}.get(momentum['state'], "📈")

    # Stall detection
    stall = (
        momentum['state'] == "LOW" and
        volatility['state'] in ("LOW", "INDECISION") and
        progress < 30
    )

    # Spike detection
    spike = volatility['state'] == "SPIKE"

    # Choppy detection
    choppy = swing_seq['trend'] in (
        "CHOPPY_EXPANDING", "CHOPPY_CONTRACTING"
    )

    update_count = sig.get('live_update_count', 0) + 1

    msg = (
        f"📊 <b>{symbol} {direction} — Update #{update_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Elapsed: <b>{elapsed_str}</b>\n"
        f"📍 Current: <b>{round(current_price, 5)}</b>\n"
        f"📈 Progress to TP1: <b>{progress}%</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Swing: <b>{swing_seq['sequence']}</b>\n"
        f"📊 Trend: <b>{swing_seq['trend']}</b>\n"
        f"{vol_emoji} Volatility: <b>{volatility['state']}</b>\n"
        f"{mom_emoji} Momentum: <b>{momentum['state']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Revised end: <b>{revised_end}</b>\n"
    )

    if stall:
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>STALL DETECTED</b>\n"
            f"Low momentum + low volatility\n"
            f"Consider: Move SL to breakeven\n"
        )

    if spike:
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚨 <b>VOLATILITY SPIKE</b>\n"
            f"Do NOT make decisions now\n"
            f"Wait for next clean candle\n"
        )

    if choppy:
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>CHOPPY MARKET</b>\n"
            f"Price alternating — reduce risk\n"
            f"Move SL to breakeven\n"
        )

    # Check news
    news_events = get_relevant_news(symbol, hours_ahead=2)
    if news_events:
        event = news_events[0]
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📰 <b>NEWS ALERT</b>\n"
            f"{event['title']} in {event['mins_until']} mins\n"
            f"Impact: {event['impact']}\n"
        )

    send_telegram(msg)

    # Update Supabase
    url = f"{SUPABASE_URL}/rest/v1/signals?id=eq.{sig['id']}"
    body = json.dumps({
        "live_update_count": update_count,
        "updated_at": datetime.utcnow().isoformat(),
    }).encode()
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/json")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        urllib.request.urlopen(req)
    except:
        pass

# ============================================================
# PART 5: CONNECT EVERYTHING TO RUN_SCAN
# ============================================================

def run_scan_enhanced(tv):
    """
    Enhanced scanner with full ICT analysis
    Replaces run_scan
    """
    print(f"\n{'='*50}")
    print(f"ZenSignals Pro — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}")

    memory = load_memory()
    signals_found = 0

    for symbol, exchange, asset_type in SYMBOLS:
        print(f"\n🔍 Scanning {symbol}...")

        # Forex session check
        if asset_type == "forex" and not is_forex_session():
            print(f"  Skipping — forex market closed")
            continue

        # Fetch all timeframes
        tf_data = fetch_all_timeframes(tv, symbol, exchange)
        if len(tf_data) < 2:
            print(f"  Insufficient data")
            continue

        # Get ref dataframe
        ref_tf = "1H" if "1H" in tf_data else list(tf_data.keys())[0]
        ref_df = tf_data[ref_tf]

        # Get indicators
        indicators = get_indicators(ref_df)

        # Score signal
        result = score_symbol(
            symbol, exchange, asset_type,
            tf_data, indicators
        )

        if result is None:
            continue

        direction = result['direction']

        # Cooldown check
        current_price = result['rr_data']['entry']
        current_atr = result['indicators']['atr']
        if is_on_cooldown(symbol, direction, current_price, memory):
            print(f"  Price hasn't moved enough — skipping")
            continue

        # ── Enhanced analysis ────────────────────────
        volatility = get_volatility_state(ref_df)
        swing_seq = analyze_swing_sequence(ref_df)
        momentum = get_momentum_state(ref_df, indicators)
        tf_model = get_ctf_itf_ttf(tf_data, direction)
        duration = calculate_duration(
            tf_model['ctf'], tf_data, direction,
            volatility, swing_seq, momentum,
            tf_model['itf_confirmed'],
            tf_model['ttf_triggered'],
            asset_type
        )
        news_events = get_relevant_news(symbol, hours_ahead=4)
        news = assess_news_impact(symbol, direction, news_events)

        # Skip if news suspension
        if news['suspend']:
            print(f"  Skipping {symbol} — news suspension: {news['message']}")
            continue

        # Skip choppy markets
        if swing_seq['trend'] in ("CHOPPY_EXPANDING",) and volatility['state'] == "INDECISION":
            print(f"  Skipping {symbol} — choppy + indecision")
            continue

        # Format and send enhanced signal
        msg = format_signal_enhanced(
            result, tf_model, duration,
            volatility, swing_seq, momentum, news
        )
        send_telegram(msg)

        # Update memory
        update_memory(
            symbol, direction,
            result['rr_data']['entry'],
            result['indicators']['atr'],
            memory
        )

        # Save to Supabase with enhanced fields
        supabase_insert({
            "symbol": symbol,
            "direction": direction,
            "score": result['score'],
            "phase": result['phase'],
            "session": result['session'],
            "entry": result['rr_data']['entry'],
            "sl": result['rr_data']['sl'],
            "tp1": result['rr_data']['tp1'],
            "tp2": result['rr_data']['tp2'],
            "rsi": result['indicators']['rsi'],
            "stoch": result['indicators']['stoch_k'],
            "adx": result['indicators']['adx'],
            "atr": result['indicators']['atr'],
            "status": "OPEN",
            "trade_type": duration['trade_type'],
            "ctf": tf_model['ctf'],
            "itf": tf_model['itf'],
            "ttf": tf_model['ttf'],
            "swing_sequence": swing_seq['sequence'],
            "volatility_state": volatility['state'],
            "momentum_state": momentum['state'],
            "conviction": volatility['conviction'],
            "estimated_duration_hours": duration['adjusted_hours'],
            "estimated_end_time": duration['end_time_iso'],
            "duration_adjustment_log": duration['adjustment_log'],
        })

        print(f"  ✅ Signal sent: {direction} {symbol} {result['score']}/24")
        print(f"  📊 {duration['trade_type']} | {duration['adjusted_hours']}h | {swing_seq['trend']}")
        signals_found += 1
        time.sleep(2)

    # Check outcomes and invalidation
    check_outcomes(tv)

    # Send live updates for open signals
    open_signals = supabase_get_open_signals()
    for sig in open_signals:
        try:
            created = datetime.fromisoformat(
                sig.get('created_at', '').replace('Z', '+00:00')
            ).replace(tzinfo=None)
            age_mins = (datetime.utcnow() - created).total_seconds() / 60
            # Send live update every 30 mins
            update_count = sig.get('live_update_count', 0)
            if age_mins > 0 and int(age_mins) % 30 == 0:
                send_live_update(sig, tv)
                time.sleep(1)
        except:
            pass

    # Hourly status update
    now = datetime.utcnow()
    if now.minute < 15:
        send_signal_updates(memory)

    print(f"\nScan complete — {signals_found} signal(s) sent")


# ============================================================
# SESSION DETECTOR + ASSET PRIORITIZATION
# ============================================================

# Asset session ratings (1-5, 0=skip)
SESSION_RATINGS = {
    "london": {
        "EURUSD": 3, "GBPUSD": 5, "USDJPY": 2,
        "AUDUSD": 1, "USDCAD": 1, "USDCHF": 2,
        "GBPJPY": 5, "EURJPY": 4, "EURGBP": 4,
        "NZDUSD": 1, "XAUUSD": 4, "XAGUSD": 3,
        "BTCUSD": 2, "ETHUSD": 2, "SOLUSD": 2,
        "BNBUSD": 2, "XRPUSD": 2,
    },
    "new_york": {
        "EURUSD": 3, "GBPUSD": 3, "USDJPY": 4,
        "AUDUSD": 2, "USDCAD": 4, "USDCHF": 3,
        "GBPJPY": 2, "EURJPY": 2, "EURGBP": 1,
        "NZDUSD": 1, "XAUUSD": 4, "XAGUSD": 3,
        "BTCUSD": 5, "ETHUSD": 5, "SOLUSD": 4,
        "BNBUSD": 4, "XRPUSD": 4,
    },
    "overlap": {
        "EURUSD": 5, "GBPUSD": 5, "USDJPY": 5,
        "AUDUSD": 2, "USDCAD": 4, "USDCHF": 4,
        "GBPJPY": 3, "EURJPY": 3, "EURGBP": 2,
        "NZDUSD": 1, "XAUUSD": 5, "XAGUSD": 4,
        "BTCUSD": 5, "ETHUSD": 5, "SOLUSD": 4,
        "BNBUSD": 4, "XRPUSD": 4,
    },
    "asian": {
        "EURUSD": 0, "GBPUSD": 0, "USDJPY": 3,
        "AUDUSD": 4, "USDCAD": 0, "USDCHF": 0,
        "GBPJPY": 1, "EURJPY": 2, "EURGBP": 0,
        "NZDUSD": 4, "XAUUSD": 2, "XAGUSD": 1,
        "BTCUSD": 1, "ETHUSD": 1, "SOLUSD": 1,
        "BNBUSD": 1, "XRPUSD": 1,
    },
    "off": {
        "EURUSD": 0, "GBPUSD": 0, "USDJPY": 0,
        "AUDUSD": 0, "USDCAD": 0, "USDCHF": 0,
        "GBPJPY": 0, "EURJPY": 0, "EURGBP": 0,
        "NZDUSD": 0, "XAUUSD": 0, "XAGUSD": 0,
        "BTCUSD": 2, "ETHUSD": 2, "SOLUSD": 1,
        "BNBUSD": 1, "XRPUSD": 1,
    },
}

# Threshold per rating
RATING_THRESHOLD = {
    5: 11,  # Peak liquidity — lowest threshold
    4: 13,  # High liquidity
    3: 15,  # Normal
    2: 18,  # Low liquidity — higher threshold
    1: 21,  # Very low — very strict
    0: 999, # Skip
}

RATING_LABEL = {
    5: "⭐⭐⭐⭐⭐ Peak liquidity",
    4: "⭐⭐⭐⭐ High liquidity",
    3: "⭐⭐⭐ Normal liquidity",
    2: "⭐⭐ Low liquidity",
    1: "⭐ Very low liquidity",
    0: "❌ Skip — no liquidity",
}


def get_current_session():
    """
    Returns current session name based on UTC time
    Handles overlap, Friday close, Monday open
    """
    now = datetime.utcnow()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    total_mins = hour * 60 + minute

    # Weekend — only crypto
    if weekday == 5:  # Saturday
        return "off"
    if weekday == 6:  # Sunday
        if total_mins < 21 * 60:  # Before 9PM UTC Sunday
            return "off"
        else:
            return "monday_open"  # Forex reopening

    # Friday close — after 8PM UTC
    if weekday == 4 and total_mins >= 20 * 60:
        return "off"

    # Monday open gap risk — first 30 mins
    if weekday == 0 and total_mins < 30:
        return "monday_open"

    # Session detection (UTC)
    if 0 <= hour < 7:
        return "asian"
    elif 7 <= hour < 12:
        return "london"
    elif 12 <= hour < 16:
        return "overlap"
    elif 16 <= hour < 20:
        return "new_york"
    else:
        return "off"


def get_session_label(session):
    labels = {
        "asian": "🌏 Asian Session",
        "london": "🇬🇧 London Session",
        "overlap": "🔥 London/NY Overlap",
        "new_york": "🗽 New York Session",
        "off": "😴 Off Session",
        "monday_open": "⚠️ Monday Open (Gap Risk)",
    }
    return labels.get(session, session)


def get_asset_rating(symbol, session):
    """
    Returns liquidity rating for asset in current session
    """
    # Overlap uses overlap ratings
    # Monday open uses higher thresholds
    if session == "monday_open":
        base = SESSION_RATINGS.get("london", {}).get(symbol, 0)
        return max(0, base - 1)  # Reduce by 1 star for gap risk

    session_map = {
        "london": "london",
        "new_york": "new_york",
        "overlap": "overlap",
        "asian": "asian",
        "off": "off",
    }
    key = session_map.get(session, "off")
    return SESSION_RATINGS.get(key, {}).get(symbol, 0)


def get_scan_threshold(symbol, session, base_threshold=15):
    """
    Returns dynamic scan threshold based on
    asset rating in current session
    """
    rating = get_asset_rating(symbol, session)

    # Monday open — add 3 to threshold
    if session == "monday_open":
        return RATING_THRESHOLD.get(rating, 999) + 3

    return RATING_THRESHOLD.get(rating, 999)


def get_priority_symbols(session):
    """
    Returns symbols sorted by session rating
    Highest rated first, skips 0-rated assets
    """
    rated = []
    for symbol, exchange, asset_type in SYMBOLS:
        rating = get_asset_rating(symbol, session)
        if rating >= 0:  # DEBUG: include all
            rated.append((rating, symbol, exchange, asset_type))

    # Sort by rating descending
    rated.sort(key=lambda x: x[0], reverse=True)
    return [(s, e, t, r) for r, s, e, t in rated]

# ============================================================
# PART 2: CORRELATION + HEDGE + GROUP ENGINE
# ============================================================

# Asset groups
ASSET_GROUPS = {
    "USD_Basket": {
        "assets": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
        "direction": "inverse",  # These move OPPOSITE to USD
        "hedge": ["USDJPY", "USDCAD", "USDCHF"],
        "hedge_direction": "same",  # Hedges move WITH USD
    },
    "GBP_Basket": {
        "assets": ["GBPUSD", "GBPJPY", "EURGBP"],
        "direction": "same",
        "hedge": ["EURUSD"],
        "hedge_direction": "inverse",
    },
    "JPY_Basket": {
        "assets": ["USDJPY", "GBPJPY", "EURJPY"],
        "direction": "same",
        "hedge": ["XAUUSD"],
        "hedge_direction": "inverse",
    },
    "Commodity_FX": {
        "assets": ["AUDUSD", "NZDUSD"],
        "direction": "same",
        "hedge": ["USDCAD"],
        "hedge_direction": "inverse",
    },
    "Metals": {
        "assets": ["XAUUSD", "XAGUSD"],
        "direction": "same",
        "hedge": ["USDJPY"],
        "hedge_direction": "inverse",
    },
    "Crypto_Majors": {
        "assets": ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD"],
        "direction": "same",
        "hedge": ["XAUUSD"],
        "hedge_direction": "inverse",
    },
}

# Conviction labels
CONVICTION_LABELS = {
    (90, 100): "🏆 EXTREMELY HIGH",
    (75, 89):  "⭐ VERY HIGH",
    (60, 74):  "✅ HIGH",
    (45, 59):  "📊 MODERATE",
    (30, 44):  "⚠️ LOW",
    (0,  29):  "❌ VERY LOW",
}

def get_conviction_label(score):
    for (low, high), label in CONVICTION_LABELS.items():
        if low <= score <= high:
            return label
    return "❌ VERY LOW"


def get_asset_group(symbol):
    """Returns which group an asset belongs to"""
    for group_name, group_data in ASSET_GROUPS.items():
        if symbol in group_data["assets"]:
            return group_name, group_data
    return None, None


def calc_dxy_bias(signal_cache):
    """
    Calculates DXY proxy from major pairs
    EURUSD(57.6%) + USDJPY(13.6%) + GBPUSD(11.9%)
    + USDCAD(9.1%) + USDCHF(3.6%) + NZDUSD(4.2%)
    """
    weights = {
        "EURUSD": -0.576,  # Negative = inverse
        "USDJPY":  0.136,
        "GBPUSD": -0.119,
        "USDCAD":  0.091,
        "USDCHF":  0.036,
        "NZDUSD": -0.042,
    }

    score = 0
    count = 0
    for symbol, weight in weights.items():
        if symbol in signal_cache:
            direction = signal_cache[symbol]
            # BUY EURUSD = USD weak = negative DXY
            val = 1 if direction == "BUY" else -1
            score += val * weight
            count += 1

    if count == 0:
        return "NEUTRAL"

    if score > 0.05:
        return "USD_STRONG"
    elif score < -0.05:
        return "USD_WEAK"
    else:
        return "NEUTRAL"


def detect_risk_environment(signal_cache):
    """
    Risk-on: crypto up + JPY weak + gold flat
    Risk-off: crypto down + JPY strong + gold up
    """
    gold_dir = signal_cache.get("XAUUSD")
    btc_dir = signal_cache.get("BTCUSD")
    jpy_pairs = [
        signal_cache.get("USDJPY"),
        signal_cache.get("GBPJPY"),
        signal_cache.get("EURJPY"),
    ]
    jpy_sells = sum(1 for d in jpy_pairs if d == "SELL")

    # Risk-off: gold up + JPY strong (USDJPY selling) + crypto down
    if gold_dir == "BUY" and jpy_sells >= 2 and btc_dir == "SELL":
        return "RISK_OFF"

    # Risk-on: gold flat/down + JPY weak + crypto up
    if btc_dir == "BUY" and jpy_sells == 0:
        return "RISK_ON"

    return "NEUTRAL"


def calc_correlation_score(symbol, direction, signal_cache):
    """
    Calculates correlation and hedge scores
    for a given signal
    """
    group_name, group_data = get_asset_group(symbol)

    if group_name is None:
        return {
            "group": "None",
            "correlation_score": 0,
            "hedge_score": 0,
            "conviction": 0,
            "conviction_label": "❌ No group",
            "correlated_assets": [],
            "hedge_assets": [],
        }

    # Check correlated assets
    group_assets = [a for a in group_data["assets"] if a != symbol]
    corr_agree = []
    corr_disagree = []

    for asset in group_assets:
        if asset not in signal_cache:
            continue
        asset_dir = signal_cache[asset]
        group_dir = group_data["direction"]

        # Same direction group
        if group_dir == "same":
            if asset_dir == direction:
                corr_agree.append(f"✅ {asset}: {asset_dir}")
            else:
                corr_disagree.append(f"❌ {asset}: {asset_dir}")
        # Inverse direction group
        else:
            opposite = "SELL" if direction == "BUY" else "BUY"
            if asset_dir == opposite:
                corr_agree.append(f"✅ {asset}: {asset_dir}")
            else:
                corr_disagree.append(f"❌ {asset}: {asset_dir}")

    # Correlation score
    total_corr = len(group_assets)
    checked_corr = len(corr_agree) + len(corr_disagree)
    corr_score = (len(corr_agree) / checked_corr * 100) if checked_corr > 0 else 50

    # Check hedge assets
    hedge_assets = group_data.get("hedge", [])
    hedge_agree = []
    hedge_disagree = []

    for asset in hedge_assets:
        if asset not in signal_cache:
            continue
        asset_dir = signal_cache[asset]
        hedge_dir = group_data.get("hedge_direction", "inverse")

        if hedge_dir == "inverse":
            opposite = "SELL" if direction == "BUY" else "BUY"
            if asset_dir == opposite:
                hedge_agree.append(f"✅ {asset}: {asset_dir}")
            else:
                hedge_disagree.append(f"❌ {asset}: {asset_dir}")
        else:
            if asset_dir == direction:
                hedge_agree.append(f"✅ {asset}: {asset_dir}")
            else:
                hedge_disagree.append(f"❌ {asset}: {asset_dir}")

    # Hedge score
    checked_hedge = len(hedge_agree) + len(hedge_disagree)
    hedge_score = (len(hedge_agree) / checked_hedge * 100) if checked_hedge > 0 else 50

    # Final conviction
    conviction = round((corr_score + hedge_score) / 2, 1)
    conviction_label = get_conviction_label(conviction)

    return {
        "group": group_name,
        "correlation_score": round(corr_score, 1),
        "hedge_score": round(hedge_score, 1),
        "conviction": conviction,
        "conviction_label": conviction_label,
        "correlated_assets": corr_agree + corr_disagree,
        "hedge_assets": hedge_agree + hedge_disagree,
    }


def get_group_trade_recommendation(symbol, direction, signal_cache):
    """
    Recommends group trade and hedge positions
    """
    group_name, group_data = get_asset_group(symbol)
    if not group_name:
        return None

    # Find all agreeing group members
    group_trades = []
    for asset in group_data["assets"]:
        if asset == symbol:
            group_trades.append(f"• {asset} {direction} ⭐ (primary)")
            continue
        if asset in signal_cache and signal_cache[asset] == direction:
            group_trades.append(f"• {asset} {direction} ✅")

    # Find hedge positions
    hedge_trades = []
    for asset in group_data.get("hedge", []):
        if asset in signal_cache:
            hedge_dir = signal_cache[asset]
            hedge_trades.append(f"• {asset} {hedge_dir} 🔀")

    return {
        "group_name": group_name,
        "group_trades": group_trades,
        "hedge_trades": hedge_trades,
    }

# ============================================================
# PART 3: FULL ENHANCED FORMATTER WITH CORRELATION + SESSION
# ============================================================

def format_signal_full(
    result, tf_model, duration, volatility,
    swing_seq, momentum, news,
    session, session_label, rating, rating_label,
    correlation, group_rec, dxy_bias, risk_env
):
    direction = result['direction']
    emoji = "🟢" if direction == "BUY" else "🔴"
    arrow = "⬆️" if direction == "BUY" else "⬇️"
    rr = result['rr_data']
    ind = result['indicators']

    type_emoji = {
        "Micro Scalp": "⚡", "Scalp": "⚡",
        "Intraday Scalp": "🎯", "Intraday": "📊",
        "Swing": "🌊", "Position": "🏦",
    }.get(duration['trade_type'], "📊")

    vol_emoji = {
        "HIGH": "🔥", "NORMAL": "✅",
        "LOW": "🐢", "SPIKE": "🚨",
        "INDECISION": "⚠️",
    }.get(volatility['state'], "✅")

    mom_emoji = {
        "VERY_HIGH": "🚀", "HIGH": "⚡",
        "MEDIUM": "📈", "LOW": "🐌",
    }.get(momentum['state'], "📈")

    swing_emoji = {
        "BULLISH_TREND": "📈", "BEARISH_TREND": "📉",
        "CHOPPY_EXPANDING": "⚠️", "CHOPPY_CONTRACTING": "🔄",
        "WEAKENING_BULL": "⚠️", "WEAKENING_BEAR": "⚠️",
        "REVERSAL_FORMING": "🔄",
    }.get(swing_seq['trend'], "📊")

    risk_emoji = {
        "RISK_ON": "🟢", "RISK_OFF": "🔴", "NEUTRAL": "⚪",
    }.get(risk_env, "⚪")

    dxy_emoji = {
        "USD_STRONG": "💪", "USD_WEAK": "📉", "NEUTRAL": "⚪",
    }.get(dxy_bias, "⚪")

    itf_status = "✅" if tf_model['itf_confirmed'] else "⏳"
    ttf_status = "✅" if tf_model['ttf_triggered'] else "⏳"

    news_line = news.get('message', 'No news data')
    news_action = news.get('action', '')

    msg = (
        f"{emoji} <b>ZenSignals Pro Alert</b> {arrow}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Pair: <b>{result['symbol']}</b>\n"
        f"📍 Signal: <b>{direction}</b>\n"
        f"📊 Score: <b>{result['score']}/24</b>\n"
        f"🔄 Phase: <b>{result['phase']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 SESSION\n"
        f"{session_label}\n"
        f"{rating_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{type_emoji} Trade Type: <b>{duration['trade_type']}</b>\n"
        f"🟢 Start: <b>{duration['start_time']}</b>\n"
        f"🔴 Est. End: <b>{duration['end_time']}</b>\n"
        f"⏳ Duration: <b>~{duration['adjusted_hours']}h</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 TIMEFRAME MODEL\n"
        f"🔵 CTF ({tf_model['ctf_label']}): Bias confirmed\n"
        f"🟡 ITF ({tf_model['itf_label']}): {itf_status}\n"
        f"🟢 TTF ({tf_model['ttf_label']}): {ttf_status}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 MARKET STRUCTURE\n"
        f"{swing_emoji} Sequence: <b>{swing_seq['sequence']}</b>\n"
        f"📊 Trend: <b>{swing_seq['trend']}</b>\n"
        f"{vol_emoji} Volatility: <b>{volatility['state']}</b> "
        f"(ATR {volatility['atr_ratio']}×)\n"
        f"🕯 Conviction: <b>{volatility['conviction']}%</b>\n"
        f"{mom_emoji} Momentum: <b>{momentum['state']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Entry: <b>{rr['entry']}</b>\n"
        f"🛑 SL: <b>{rr['sl']}</b>\n"
        f"🎯 TP1 (1:2): <b>{rr['tp1']}</b>\n"
        f"🏆 TP2 (1:3): <b>{rr['tp2']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 RSI: <b>{ind['rsi']}</b>\n"
        f"📉 Stoch: <b>{ind['stoch_k']}</b>\n"
        f"💪 ADX: <b>{ind['adx']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 CORRELATION\n"
        f"👥 Group: <b>{correlation['group']}</b>\n"
        f"📊 Corr: <b>{correlation['correlation_score']}%</b>\n"
        f"🔀 Hedge: <b>{correlation['hedge_score']}%</b>\n"
        f"🏆 Conviction: <b>{correlation['conviction_label']}</b>\n"
    )

    # Correlated assets
    if correlation['correlated_assets']:
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += "🔗 CORRELATED ASSETS\n"
        for a in correlation['correlated_assets'][:4]:
            msg += f"{a}\n"

    # Hedge assets
    if correlation['hedge_assets']:
        msg += "🔀 HEDGE POSITIONS\n"
        for a in correlation['hedge_assets'][:3]:
            msg += f"{a}\n"

    # Group trade recommendation
    if group_rec and len(group_rec['group_trades']) > 1:
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 GROUP TRADE\n"
        )
        for t in group_rec['group_trades'][:4]:
            msg += f"{t}\n"
        msg += "⚡ Reduce each to 0.5× size\n"

    # Hedge recommendation
    if group_rec and group_rec['hedge_trades']:
        msg += "🔀 HEDGE OPPORTUNITY\n"
        for t in group_rec['hedge_trades'][:2]:
            msg += f"{t}\n"

    # Market environment
    msg += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌍 MARKET ENVIRONMENT\n"
        f"{risk_emoji} Risk: <b>{risk_env}</b>\n"
        f"{dxy_emoji} DXY: <b>{dxy_bias}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📰 NEWS: {news_line}\n"
    )

    if news_action:
        msg += f"⚡ Action: <i>{news_action}</i>\n"

    msg += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 Time: <b>{duration['start_time']}</b>\n"
        f"⚠️ <i>Always confirm before entering</i>"
    )

    return msg

# ============================================================
# PART 4: FINAL RUN_SCAN_FULL — CONNECTS EVERYTHING
# ============================================================

def run_scan_enhanced(tv):
    print(f"\n{'='*50}")
    print(f"ZenSignals Pro FULL — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}")

    memory = load_memory()
    signals_found = 0

    # Get current session
    session = get_current_session()
    session_label = get_session_label(session)
    print(f"\n{session_label}")

    # Get priority-sorted symbols for this session
    priority_symbols = get_priority_symbols(session)
    print(f"Scanning {len(priority_symbols)} assets for {session} session")

    # Signal cache for correlation
    signal_cache = {}

    # First pass — quick bias scan to build signal cache
    print("\nBuilding signal cache for correlation...")
    for symbol, exchange, asset_type, rating in priority_symbols:
        if rating < 2:
            continue
        try:
            df = get_data(tv, symbol, exchange, "1H")
            if df is None:
                continue
            bos = detect_bos(df)
            if bos:
                signal_cache[symbol] = bos
            time.sleep(0.5)
        except:
            continue

    # Calculate market-wide metrics
    dxy_bias = calc_dxy_bias(signal_cache)
    risk_env = detect_risk_environment(signal_cache)
    print(f"DXY: {dxy_bias} | Risk: {risk_env}")

    # Second pass — full analysis on priority assets
    for symbol, exchange, asset_type, rating in priority_symbols:

        print(f"\n🔍 Scanning {symbol} (⭐×{rating})...")

        # Get dynamic threshold
        threshold = get_scan_threshold(symbol, session)
        if threshold >= 999:
            print(f"  Skipping — no liquidity this session")
            continue

        # Forex session check
        if asset_type == "forex" and session in ("off",):
            print(f"  Skipping — forex market closed")
            continue

        # Fetch all timeframes
        tf_data = fetch_all_timeframes(tv, symbol, exchange)
        if len(tf_data) < 2:
            print(f"  Insufficient data")
            continue

        # Get ref dataframe
        ref_tf = "1H" if "1H" in tf_data else list(tf_data.keys())[0]
        ref_df = tf_data[ref_tf]

        # Get indicators
        indicators = get_indicators(ref_df)

        # Score with dynamic threshold
        result = score_symbol(
            symbol, exchange, asset_type,
            tf_data, indicators,
        )

        if result is None:
            continue

        # Apply session threshold
        if result['score'] < threshold:
            print(f"  Score {result['score']} below session threshold {threshold}")
            continue

        direction = result['direction']

        # Cooldown check
        current_price = result['rr_data']['entry']
        current_atr = result['indicators']['atr']
        if is_on_cooldown(symbol, direction, current_price, memory):
            print(f"  Price hasn't moved enough — skipping")
            continue

        # Enhanced analysis
        volatility = get_volatility_state(ref_df)
        swing_seq = analyze_swing_sequence(ref_df)
        momentum = get_momentum_state(ref_df, indicators)
        tf_model = get_ctf_itf_ttf(tf_data, direction)
        duration = calculate_duration(
            tf_model['ctf'], tf_data, direction,
            volatility, swing_seq, momentum,
            tf_model['itf_confirmed'],
            tf_model['ttf_triggered'],
            asset_type
        )

        # News check
        news_events = get_relevant_news(symbol, hours_ahead=4)
        news = assess_news_impact(symbol, direction, news_events)

        # Skip if news suspension
        if news['suspend']:
            print(f"  News suspension: {news['message']}")
            continue

        # Skip choppy + indecision
        if swing_seq['trend'] in ("CHOPPY_EXPANDING",) and volatility['state'] == "INDECISION":
            print(f"  Choppy + indecision — skipping")
            continue

        # Correlation analysis
        correlation = calc_correlation_score(symbol, direction, signal_cache)
        group_rec = get_group_trade_recommendation(symbol, direction, signal_cache)

        # Rating info
        rating_label = RATING_LABEL.get(rating, "")

        # Format full signal
        msg = format_signal_full(
            result, tf_model, duration,
            volatility, swing_seq, momentum, news,
            session, session_label, rating, rating_label,
            correlation, group_rec, dxy_bias, risk_env
        )

        send_telegram(msg)

        # Update memory
        update_memory(
            symbol, direction,
            result['rr_data']['entry'],
            result['indicators']['atr'],
            memory
        )

        # Save to Supabase
        supabase_insert({
            "symbol": symbol,
            "direction": direction,
            "score": result['score'],
            "phase": result['phase'],
            "session": session_label,
            "entry": result['rr_data']['entry'],
            "sl": result['rr_data']['sl'],
            "tp1": result['rr_data']['tp1'],
            "tp2": result['rr_data']['tp2'],
            "rsi": result['indicators']['rsi'],
            "stoch": result['indicators']['stoch_k'],
            "adx": result['indicators']['adx'],
            "atr": result['indicators']['atr'],
            "status": "OPEN",
            "trade_type": duration['trade_type'],
            "ctf": tf_model['ctf'],
            "itf": tf_model['itf'],
            "ttf": tf_model['ttf'],
            "swing_sequence": swing_seq['sequence'],
            "volatility_state": volatility['state'],
            "momentum_state": momentum['state'],
            "conviction": volatility['conviction'],
            "estimated_duration_hours": duration['adjusted_hours'],
            "estimated_end_time": duration['end_time_iso'],
            "duration_adjustment_log": duration['adjustment_log'],
            "session_rating": rating,
            "session_name": session,
            "liquidity_label": rating_label,
            "correlation_score": correlation['correlation_score'],
            "hedge_score": correlation['hedge_score'],
            "conviction_label": correlation['conviction_label'],
            "group_name": correlation['group'],
            "correlated_assets": ", ".join(correlation['correlated_assets']),
            "hedge_assets": ", ".join(correlation['hedge_assets']),
            "risk_environment": risk_env,
            "dxy_bias": dxy_bias,
            "scan_threshold": threshold,
        })

        print(f"  ✅ Signal: {direction} {symbol} {result['score']}/24 | ⭐×{rating} | {duration['trade_type']}")
        signals_found += 1
        time.sleep(2)

    # Check outcomes
    check_outcomes(tv)

    # Live updates for open signals
    open_signals = supabase_get_open_signals()
    for sig in open_signals:
        try:
            created = datetime.fromisoformat(
                sig.get('created_at', '').replace('Z', '+00:00')
            ).replace(tzinfo=None)
            age_mins = (datetime.utcnow() - created).total_seconds() / 60
            update_count = sig.get('live_update_count', 0)
            if age_mins > 0 and int(age_mins) % 30 == 0:
                send_live_update(sig, tv)
                time.sleep(1)
        except:
            pass

    # Hourly status
    now = datetime.utcnow()
    if now.minute < 15:
        send_signal_updates(memory)

    print(f"\nScan complete — {signals_found} signal(s) sent")
    print(f"Session: {session_label} | DXY: {dxy_bias} | Risk: {risk_env}")

# ============================================================
# SCALP SCANNER
# ============================================================

SCALP_COOLDOWN_DICT = {}
SCALP_TTL = {
    "3M": 10, "5M": 20, "15M": 30,
    "30M": 45, "1H": 60
}

def is_scalp_killzone():
    now = datetime.utcnow()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()
    total = hour * 60 + minute

    # Weekend — forex killzones inactive
    if weekday >= 5:
        # Crypto Asian window still valid on weekends
        return (0 <= total <= 240) or (840 <= total <= 1080)

    # Forex killzones (UTC)
    london = (420 <= total <= 600)      # 7AM-10AM UTC
    ny = (720 <= total <= 960)           # 12PM-4PM UTC
    overlap = (720 <= total <= 900)      # 12PM-3PM UTC

    # Crypto additional windows (UTC)
    crypto_asian = (0 <= total <= 240)   # 12AM-4AM UTC (Asian crypto)
    crypto_eu = (600 <= total <= 720)    # 10AM-12PM UTC (EU crypto)

    return london or ny or overlap or crypto_asian or crypto_eu


def get_scalp_asset_type(symbol):
    crypto = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD"]
    metals = ["XAUUSD", "XAGUSD"]
    if symbol in crypto:
        return "crypto"
    elif symbol in metals:
        return "metal"
    return "forex"


def is_valid_scalp_window(symbol):
    """
    Checks if current time is valid scalp window
    for the specific asset type
    """
    now = datetime.utcnow()
    hour = now.hour
    total = now.hour * 60 + now.minute
    weekday = now.weekday()
    asset_type = get_scalp_asset_type(symbol)

    if asset_type == "crypto":
        # Crypto valid 24/7 but prioritize these windows
        # Asian: 12AM-4AM UTC
        # London: 7AM-10AM UTC
        # NY/Overlap: 12PM-4PM UTC
        # EU pre-market: 6AM-8AM UTC
        asian = (0 <= total <= 240)
        london = (420 <= total <= 600)
        ny = (720 <= total <= 960)
        eu_pre = (360 <= total <= 480)
        # On weekends crypto always valid
        if weekday >= 5:
            return True
        return asian or london or ny or eu_pre

    elif asset_type == "metal":
        # Metals follow forex + Asian demand window
        if weekday >= 5:
            return (0 <= total <= 240)
        asian_metals = (0 <= total <= 300)   # 12AM-5AM
        london = (420 <= total <= 600)
        ny = (720 <= total <= 960)
        return asian_metals or london or ny

    else:
        # Forex — strict killzones only, weekdays only
        if weekday >= 5:
            return False
        london = (420 <= total <= 600)
        ny = (720 <= total <= 960)
        return london or ny

def run_scalp_scan(tv):
    print(f"\n{'='*50}")
    print("⚡ ZenSignals SCALP Scanner")
    found = 0
    session = get_current_session()
    priority = get_priority_symbols(session)
    scalp_symbols = [(s, e, t, r) for s, e, t, r in priority if r >= 3]

    for symbol, exchange, asset_type, rating in scalp_symbols:
        try:
            if not is_valid_scalp_window(symbol):
                print(f"  {symbol} outside scalp window")
                continue

            print(f"\n⚡ Scalp {symbol} (⭐x{rating})...")

            df_1h = get_data(tv, symbol, exchange, "1H")
            df_15m = get_data(tv, symbol, exchange, "15M")
            df_5m = get_data(tv, symbol, exchange, "5M")

            if df_1h is None or df_15m is None:
                continue

            htf_bos = detect_bos(df_1h)
            if htf_bos is None:
                continue

            direction = htf_bos
            indicators = get_indicators(df_15m)
            rsi = indicators.get("rsi", 50)
            stoch = indicators.get("stoch_k", 50)
            adx = indicators.get("adx", 0)
            atr = indicators.get("atr", 0.001)

            score = 0
            reasons = []

            # 1. Kill zone
            score += 20
            reasons.append("Killzone ✅")

            # 2. HTF BOS
            score += 20
            reasons.append(f"1H BOS {direction} ✅")

            # 3. Liquidity sweep on 15M
            if detect_liquidity_sweep(df_15m, direction):
                score += 15
                reasons.append("Liquidity sweep ✅")
            else:
                continue

            # 4. CHoCH on 15M
            choch = detect_choch(df_15m)
            if choch == direction:
                score += 15
                reasons.append("CHoCH ✅")

            # 5. OB on 15M
            ob = detect_order_block(df_15m, direction)
            if ob:
                score += 10
                reasons.append("Order Block ✅")

            # 6. FVG on 15M
            fvg = detect_fvg(df_15m, direction)
            if fvg:
                score += 10
                reasons.append("FVG ✅")

            # 7. RSI confirmation
            if direction == "BUY" and rsi < 40:
                score += 10
                reasons.append(f"RSI oversold {rsi} ✅")
            elif direction == "SELL" and rsi > 60:
                score += 10
                reasons.append(f"RSI overbought {rsi} ✅")

            # 8. Stoch confirmation
            if direction == "BUY" and stoch < 25:
                score += 5
                reasons.append(f"Stoch oversold {stoch} ✅")
            elif direction == "SELL" and stoch > 75:
                score += 5
                reasons.append(f"Stoch overbought {stoch} ✅")

            # 9. ADX trending
            if adx > 25:
                score += 5
                reasons.append(f"ADX trending {adx} ✅")

            # 10. Delta approximation
            try:
                cr = df_15m["high"].iloc[-1] - df_15m["low"].iloc[-1]
                if cr > 0:
                    delta = (df_15m["close"].iloc[-1] - df_15m["low"].iloc[-1]) / cr
                    if direction == "BUY" and delta > 0.7:
                        score += 15
                        reasons.append(f"Delta bullish {delta:.2f} ✅")
                    elif direction == "SELL" and delta < 0.3:
                        score += 15
                        reasons.append(f"Delta bearish {delta:.2f} ✅")
            except Exception:
                pass

            # 11. Volume anomaly
            try:
                vol = df_15m["volume"]
                avg_vol = vol.iloc[-20:-1].mean()
                if avg_vol > 0 and vol.iloc[-1] > avg_vol * 2:
                    score += 10
                    reasons.append(f"Vol spike {vol.iloc[-1]/avg_vol:.1f}x ✅")
            except Exception:
                pass

            # 12. Wick rejection
            try:
                body = abs(df_15m["close"].iloc[-1] - df_15m["open"].iloc[-1])
                cr2 = df_15m["high"].iloc[-1] - df_15m["low"].iloc[-1]
                if cr2 > 0 and (1 - body/cr2) > 0.6:
                    score += 10
                    reasons.append(f"Wick rejection ✅")
            except Exception:
                pass

            # 13. Efficiency ratio
            try:
                closes = df_15m["close"].iloc[-10:]
                net = abs(closes.iloc[-1] - closes.iloc[0])
                total = closes.diff().abs().sum()
                if total > 0 and net/total > 0.6:
                    score += 10
                    reasons.append(f"Efficiency ✅")
            except Exception:
                pass

            # 14. Sweep + absorption
            try:
                rh = df_15m["high"].iloc[-20:-2].max()
                rl = df_15m["low"].iloc[-20:-2].min()
                lh = df_15m["high"].iloc[-2]
                ll = df_15m["low"].iloc[-2]
                lc = df_15m["close"].iloc[-1]
                if direction == "BUY" and ll < rl and lc > rl:
                    score += 15
                    reasons.append("Sweep+absorption BUY ✅")
                elif direction == "SELL" and lh > rh and lc < rh:
                    score += 15
                    reasons.append("Sweep+absorption SELL ✅")
            except Exception:
                pass

            # Minimum score
            if score < 60:
                print(f"  Score {score}/160 — below threshold | reasons: {reasons}")
                continue

            # Cooldown check
            cooldown_key = f"{symbol}_scalp"
            if cooldown_key in SCALP_COOLDOWN_DICT:
                elapsed = (datetime.utcnow() - SCALP_COOLDOWN_DICT[cooldown_key]).total_seconds() / 60
                if elapsed < 30:
                    print(f"  Scalp cooldown — {int(30-elapsed)} mins remaining")
                    continue

            # Calculate RR
            rr = calc_rr(df_15m, direction, ob, atr)
            if rr is None:
                continue

            # Format and send
            arrow = "📈" if direction == "BUY" else "📉"
            emoji = "🟢" if direction == "BUY" else "🔴"
            ny = pytz.timezone("America/New_York")
            now_str = datetime.now(ny).strftime("%Y-%m-%d %H:%M")

            msg = (
                f"⚡ <b>SCALP ALERT</b> {emoji} {arrow}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 Pair: <b>{symbol}</b>\n"
                f"📍 Signal: <b>{direction}</b>\n"
                f"⭐ Rating: <b>{'⭐'*rating}</b>\n"
                f"🎯 Score: <b>{score}/160</b>\n"
                f"⏱ Timeframe: <b>15M</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Entry: <b>{rr['entry']}</b>\n"
                f"🛑 SL: <b>{rr['sl']}</b>\n"
                f"🎯 TP1 (1:2): <b>{rr['tp1']}</b>\n"
                f"🏆 TP2 (1:3): <b>{rr['tp2']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Confluence:\n"
            )
            for r in reasons:
                msg += f"  • {r}\n"
            msg += (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Move SL to BE at TP1\n"
                f"⏰ TTL: 30 mins\n"
                f"🕐 {now_str} NY\n"
                f"⚠️ <i>Always confirm before entering</i>"
            )

            send_telegram(msg)
            SCALP_COOLDOWN_DICT[cooldown_key] = datetime.utcnow()
            found += 1
            print(f"  ✅ Scalp signal: {symbol} {direction} {score}/160")
            time.sleep(1)

        except Exception as e:
            print(f"  Error: {e}")
            continue

    print(f"\n⚡ Scalp scan complete — {found} signal(s)")

