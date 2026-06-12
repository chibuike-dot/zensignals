import os, sys, json, requests
from datetime import datetime
import pytz

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SYMBOL_EXCHANGE = {
    "EURUSD": "FX_IDC", "GBPUSD": "FX_IDC", "USDJPY": "FX_IDC",
    "AUDUSD": "FX_IDC", "USDCAD": "FX_IDC", "USDCHF": "FX_IDC",
    "GBPJPY": "FX_IDC", "EURJPY": "FX_IDC", "EURGBP": "FX_IDC",
    "NZDUSD": "FX_IDC", "XAUUSD": "OANDA", "XAGUSD": "OANDA",
    "BTCUSD": "COINBASE", "ETHUSD": "COINBASE", "SOLUSD": "COINBASE",
    "BNBUSD": "BINANCE", "XRPUSD": "COINBASE",
}

GIST_ID = os.environ["GIST_ID"]
GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
FILENAME = "zensignals_data.json"
GIST_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def read_gist():
    r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=GIST_HEADERS)
    content = r.json()["files"][FILENAME]["content"]
    return json.loads(content)

def write_gist(data):
    requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers=GIST_HEADERS,
        json={"files": {FILENAME: {"content": json.dumps(data, indent=2)}}}
    )

def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    )

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
    data = read_gist()
    signals = [s for s in data["signals"] if s.get("status") == "OPEN"]
    if not signals:
        print("No open trades")
        return

    ny = pytz.timezone("America/New_York")
    now_str = datetime.now(ny).strftime("%Y-%m-%d %H:%M")
    updates = []
    changed = False

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
            sig["status"] = status
            changed = True
            updates.append(
                f"{emoji}\n"
                f"📌 <b>{symbol}</b> {direction}\n"
                f"💰 Entry: {entry} → Now: {price}\n"
                f"⏰ {now_str} NY"
            )

    if changed:
        write_gist(data)
    if updates:
        send_telegram("🔔 <b>Trade Update</b>\n\n" + "\n\n".join(updates))
    else:
        print("No trades closed this cycle")

def pnl_summary():
    data = read_gist()
    sigs = data["signals"]
    total = len(sigs)
    wins = sum(1 for s in sigs if s["status"] == "WIN")
    losses = sum(1 for s in sigs if s["status"] == "LOSS")
    open_t = sum(1 for s in sigs if s["status"] == "OPEN")
    winrate = round(wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    send_telegram(
        f"💹 <b>ZenSignals P&L Summary</b>\n\n"
        f"Total Signals: {total}\n"
        f"✅ Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"📊 Win Rate: {winrate}%\n"
        f"🔓 Open: {open_t}"
    )

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pnl":
        pnl_summary()
    else:
        check_open_trades()
