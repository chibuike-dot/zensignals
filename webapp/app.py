from flask import Flask, jsonify, render_template_string
import urllib.request
import json

app = Flask(__name__)

SUPABASE_URL = "https://bnonwdvjjibxukkicpla.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJub253ZHZqamlieHVra2ljcGxhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA4MzY0MDUsImV4cCI6MjA5NjQxMjQwNX0.VFUCJZGGmBso7GOTNBBcmPqHfR0vdBpLgizbBd4gaGU"
TELEGRAM_TOKEN = "8838997298:AAHLpLhWCjeHcAcNbhlzUThRjvzyc7bXCsc"
CHAT_ID = "6517653689"

def get_signals(status=None, limit=20):
    url = f"{SUPABASE_URL}/rest/v1/signals?order=created_at.desc&limit={limit}"
    if status:
        url += f"&status=eq.{status}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except:
        return []

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req)
    except:
        pass

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    from flask import request
    data = request.json
    if not data or "message" not in data:
        return jsonify({"ok": True})

    text = data["message"].get("text", "").strip().lower()
    chat_id = data["message"]["chat"]["id"]

    if text == "/status":
        signals = get_signals(status="OPEN", limit=10)
        if not signals:
            send_telegram("No open signals currently.")
        else:
            msg = "📊 <b>Open Signals</b>\n━━━━━━━━━━━━━━━━━━\n"
            for s in signals:
                emoji = "🟢" if s["direction"] == "BUY" else "🔴"
                msg += (
                    f"{emoji} <b>{s['symbol']}</b> {s['direction']}\n"
                    f"   Entry: {s['entry']} | Score: {s['score']}/24\n"
                    f"   TP1: {s['tp1']} | SL: {s['sl']}\n\n"
                )
            send_telegram(msg)

    elif text == "/history":
        signals = get_signals(limit=10)
        if not signals:
            send_telegram("No signal history yet.")
        else:
            msg = "📜 <b>Last 10 Signals</b>\n━━━━━━━━━━━━━━━━━━\n"
            for s in signals:
                emoji = "🟢" if s["direction"] == "BUY" else "🔴"
                outcome = s.get("outcome") or s.get("status", "OPEN")
                msg += f"{emoji} {s['symbol']} {s['direction']} — {outcome}\n"
            send_telegram(msg)

    elif text == "/pnl":
        signals = get_signals(limit=100)
        closed = [s for s in signals if s.get("status") == "CLOSED"]
        wins = [s for s in closed if s.get("outcome") in ("TP1_HIT", "TP2_HIT")]
        losses = [s for s in closed if s.get("outcome") == "SL_HIT"]
        total = len(closed)
        win_rate = round(len(wins) / total * 100, 1) if total > 0 else 0
        msg = (
            f"💹 <b>ZenSignals P&L Summary</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Total Signals: {total}\n"
            f"✅ Wins: {len(wins)}\n"
            f"❌ Losses: {len(losses)}\n"
            f"📊 Win Rate: {win_rate}%\n"
            f"🔓 Open: {len([s for s in signals if s.get('status') == 'OPEN'])}"
        )
        send_telegram(msg)

    elif text == "/help":
        send_telegram(
            "🤖 <b>ZenSignals Bot Commands</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/status — View open signals\n"
            "/history — Last 10 signals\n"
            "/pnl — Win/loss summary\n"
            "/help — This menu"
        )

    return jsonify({"ok": True})

@app.route("/dashboard")
def dashboard():
    signals = get_signals(limit=50)
    closed = [s for s in signals if s.get("status") == "CLOSED"]
    wins = len([s for s in closed if s.get("outcome") in ("TP1_HIT", "TP2_HIT")])
    losses = len([s for s in closed if s.get("outcome") == "SL_HIT"])
    win_rate = round(wins / len(closed) * 100, 1) if closed else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ZenSignals Pro Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0a0a0f; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }}
.header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 20px; text-align: center; border-bottom: 1px solid #00d4ff33; }}
.header h1 {{ color: #00d4ff; font-size: 24px; }}
.header p {{ color: #888; font-size: 12px; margin-top: 4px; }}
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 20px; }}
.stat {{ background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 16px; text-align: center; }}
.stat .num {{ font-size: 28px; font-weight: bold; color: #00d4ff; }}
.stat .label {{ font-size: 11px; color: #6b7280; margin-top: 4px; }}
.signals {{ padding: 0 20px 20px; }}
.signals h2 {{ color: #00d4ff; margin-bottom: 12px; font-size: 16px; }}
.signal-card {{ background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; }}
.signal-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
.symbol {{ font-weight: bold; font-size: 15px; }}
.buy {{ color: #10b981; }}
.sell {{ color: #ef4444; }}
.score {{ background: #1f2937; padding: 2px 8px; border-radius: 20px; font-size: 12px; }}
.signal-info {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; font-size: 11px; color: #9ca3af; }}
.outcome {{ padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: bold; }}
.OPEN {{ background: #1f2937; color: #60a5fa; }}
.TP1_HIT, .TP2_HIT {{ background: #064e3b; color: #10b981; }}
.SL_HIT {{ background: #7f1d1d; color: #ef4444; }}
</style>
</head>
<body>
<div class="header">
  <h1>⚡ ZenSignals Pro</h1>
  <p>Institutional ICT/SMC Scanner — 17 Assets — 6 Timeframes</p>
</div>
<div class="stats">
  <div class="stat"><div class="num">{len(signals)}</div><div class="label">Total Signals</div></div>
  <div class="stat"><div class="num" style="color:#10b981">{wins}</div><div class="label">Wins</div></div>
  <div class="stat"><div class="num" style="color:#ef4444">{losses}</div><div class="label">Losses</div></div>
  <div class="stat"><div class="num">{win_rate}%</div><div class="label">Win Rate</div></div>
</div>
<div class="signals">
  <h2>📊 Recent Signals</h2>
"""
    for s in signals:
        direction_class = "buy" if s["direction"] == "BUY" else "sell"
        outcome = s.get("outcome") or "OPEN"
        status = s.get("status", "OPEN")
        outcome_display = outcome if outcome != "OPEN" else status
        created = s.get("created_at", "")[:16].replace("T", " ")
        html += f"""
  <div class="signal-card">
    <div class="signal-top">
      <span class="symbol {direction_class}">{s['symbol']} {s['direction']}</span>
      <span class="score">⭐ {s['score']}/24</span>
      <span class="outcome {outcome_display}">{outcome_display}</span>
    </div>
    <div class="signal-info">
      <span>Entry: {s['entry']}</span>
      <span>TP1: {s['tp1']}</span>
      <span>SL: {s['sl']}</span>
      <span>RSI: {s['rsi']}</span>
      <span>ADX: {s['adx']}</span>
      <span>{created}</span>
    </div>
  </div>"""

    html += """
</div>
</body>
</html>"""
    return html

@app.route("/")
def index():
    return jsonify({"status": "ZenSignals Pro API running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
