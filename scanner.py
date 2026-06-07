# ============================================================
# ZENSIGNALS PRO - Institutional ICT/SMC Scanner
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

def get_data(tv, symbol, exchange, tf_key, retries=3):
    interval = get_interval(tf_key)
    for i in range(retries):
        try:
            df = tv.get_hist(symbol, exchange, interval=interval, n_bars=200)
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

def get_current_session():
    utc_hour = datetime.now(pytz.utc).hour
    for name, (start, end) in KILLZONES.items():
        if start <= utc_hour < end:
            return name
    return None

def is_in_killzone():
    return get_current_session() is not None

def load_memory():
    if os.path.exists(SIGNAL_MEMORY_FILE):
        with open(SIGNAL_MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(SIGNAL_MEMORY_FILE, "w") as f:
        json.dump(memory, f)

def is_on_cooldown(symbol, direction, memory):
    key = f"{symbol}_{direction}"
    if key not in memory:
        return False
    last_time = datetime.fromisoformat(memory[key])
    elapsed = datetime.utcnow() - last_time
    return elapsed < timedelta(hours=COOLDOWN_HOURS)

def update_memory(symbol, direction, memory):
    key = f"{symbol}_{direction}"
    memory[key] = datetime.utcnow().isoformat()
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

    session = get_current_session()
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
        if is_on_cooldown(symbol, result['direction'], memory):
            print(f"  On cooldown — skipping")
            continue
        msg = format_signal(result)
        send_telegram(msg)
        update_memory(symbol, result['direction'], memory)
        print(f"  ✅ Signal sent: {result['direction']} {symbol} {result['score']}/24")
        signals_found += 1
        time.sleep(2)
    print(f"\nScan complete — {signals_found} signal(s) sent")

if __name__ == "__main__":
    from tvDatafeed import TvDatafeed
    print("🚀 ZenSignals Pro starting...")
    tv = TvDatafeed()
    send_telegram(
        "🚀 <b>ZenSignals Pro Started</b>\n"
        "Institutional ICT/SMC Scanner\n"
        "17 assets — 6 timeframes\n"
        "Min score: 15/24"
    )
    run_scan(tv)
