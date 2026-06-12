import os, urllib.request, json, sys
from datetime import datetime
import pytz

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Full symbol->exchange map matching scanner.py SYMBOLS list
SYMBOL_EXCHANGE = {
    "EURUSD": "FX_IDC", "GBPUSD": "FX_IDC", "USDJPY": "FX_IDC",
    "AUDUSD": "FX_IDC", "USDCAD": "FX_IDC", "USDCHF": "FX_IDC",
    "GBPJPY": "FX_IDC", "EURJPY": "FX_IDC", "EURGBP": "FX_IDC",
    "NZDUSD": "FX_IDC", "XAUUSD": "OANDA", "XAGUSD": "OANDA",
    "BTCUSD": "COINBASE", "ETHUSD": "COINBASE", "SOLUSD": "COINBASE",
    "BNBUSD": "BINANCE", "XRPUSD": "COINBASE",
}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/json")
    urllib.request.urlopen(req)

def supabase_get(query):
    url = f"{SUPABASE_URL}/rest/v1/signals?{query}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    return json.loads(urllib.request.urlopen(req).read())

def supabase_patch(signal_id, data):
    url = f"{SUPABASE_URL}/rest/v1/signals?id=eq.{signal_id}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    urllib.request.urlopen(req)

def get_current_price(symbol):
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    exchange = SYMBOL_EXCHANGE.get(symbol, "FX_IDC")
    try:
        df = tv.get_hist(symbol, exchange, interval=Interval.in_1_hour, n_bars=2)
        if df is not None and len(df) > 0:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None

def check_open_trades():
    signals = supabase_get("status=eq.OPEN&order=created_at.desc")
    if not signals:
        print("No open trades")
        return

    ny = pytz.timezone("America/New_York")
    now_str = datetime.now(ny).strftime("%Y-%m-%d %H:%M")
    updates = []

    for sig in signals:
        symbol = sig.get("symbol")
        direction = sig.get("direction")
        entry = float(sig.get("entry") or 0)
        sl = float(sig.get("sl") or 0)
        tp1 = float(sig.get("tp1") or 0)
        tp2 = float(sig.get("tp2") or 0)
        sig_id = sig.get("id")

        price = get_current_price(symbol)
        if not price:
            continue

        status = None
        emoji = ""
        if direction == "BUY":
            if price >= tp2:
                status = "WIN"; emoji = "🏆 TP2 Hit"
            elif price >= tp1:
                status = "WIN"; emoji = "🎯 TP1 Hit"
            elif price <= sl:
                status = "LOSS"; emoji = "❌ SL Hit"
        else:
            if price <= tp2:
                status = "WIN"; emoji = "🏆 TP2 Hit"
            elif price <= tp1:
                status = "WIN"; emoji = "🎯 TP1 Hit"
            elif price >= sl:
                status = "LOSS"; emoji = "❌ SL Hit"

        if status:
            supabase_patch(sig_id, {"status": status})
            updates.append(
                f"{emoji}\n"
                f"📌 <b>{symbol}</b> {direction}\n"
                f"💰 Entry: {entry} → Now: {price}\n"
                f"⏰ {now_str} NY"
            )

    if updates:
        send_telegram("🔔 <b>Trade Update</b>\n\n" + "\n\n".join(updates))
    else:
        print("No trades closed this cycle")

def pnl_summary():
    all_sigs = supabase_get("order=created_at.desc&limit=200")
    total = len(all_sigs)
    wins = sum(1 for s in all_sigs if s.get("status") == "WIN")
    losses = sum(1 for s in all_sigs if s.get("status") == "LOSS")
    open_t = sum(1 for s in all_sigs if s.get("status") == "OPEN")
    winrate = round(wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    msg = (
        f"💹 <b>ZenSignals P&L Summary</b>\n\n"
        f"Total Signals: {total}\n"
        f"✅ Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"📊 Win Rate: {winrate}%\n"
        f"🔓 Open: {open_t}"
    )
    send_telegram(msg)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pnl":
        pnl_summary()
    else:
        check_open_trades()
