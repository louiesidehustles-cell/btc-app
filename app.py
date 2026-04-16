from flask import Flask, jsonify, send_file
import requests, json, os, threading, time
from datetime import datetime

app = Flask(__name__)

BASE_DIR = "/data"
DATA_FILE = f"{BASE_DIR}/data.json"
HISTORY_FILE = f"{BASE_DIR}/history.json"
PRICE_FILE = f"{BASE_DIR}/prices.json"

START_BALANCE = 2000
TRADE_SIZE = 100
FEE = 0.001  # 0.1%

price_cache = {}

# ================= INIT =================
def init_files():
    os.makedirs(BASE_DIR, exist_ok=True)

    for f, default in [
        (DATA_FILE, {"open_trades": []}),
        (HISTORY_FILE, {"strategyA":{}, "strategyB":{}}),
        (PRICE_FILE, [])
    ]:
        if not os.path.exists(f):
            json.dump(default, open(f, "w"))

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

# ================= PRICE =================
def update_price():
    global price_cache
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price").json()
        price_cache = {x["symbol"]: float(x["price"]) for x in res}
    except:
        pass

def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]
    data = [{"symbol": s, "price": price_cache.get(s, 0)} for s in symbols]
    save_json(PRICE_FILE, data)

# ================= INDICATORS =================
def ema(prices, p):
    k = 2/(p+1)
    e=[prices[0]]
    for x in prices[1:]:
        e.append(x*k + e[-1]*(1-k))
    return e

def rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1,len(prices)):
        diff = prices[i]-prices[i-1]
        gains.append(max(diff,0))
        losses.append(abs(min(diff,0)))
    avg_gain = sum(gains[-period:])/period
    avg_loss = sum(losses[-period:])/period
    if avg_loss == 0: return 100
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def calculate_risk(price, ema20, ema50, rsi_val):
    score = 0
    if price > ema20 > ema50: score+=2
    elif price > ema20: score+=1

    if 50 < rsi_val < 65: score+=2
    elif rsi_val < 70: score+=1

    return max(1,min(5,score))

# ================= FETCH 7 DAYS =================
def get_7d_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"
    all_data = []
    end = int(time.time()*1000)

    for _ in range(10):  # pagination
        params = {
            "symbol": symbol,
            "interval": "5m",
            "limit": 1000,
            "endTime": end
        }
        data = requests.get(url, params=params).json()
        if not data: break
        all_data = data + all_data
        end = data[0][0] - 1
        time.sleep(0.1)

    return all_data

# ================= BACKTEST =================
def run_strategy(no_sl=False):
    balance = START_BALANCE
    open_trades = []
    history = {}

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]

    for sym in symbols:
        klines = get_7d_klines(sym)

        closes = [float(k[4]) for k in klines]
        times = [k[0] for k in klines]

        for i in range(50,len(closes)):

            price = closes[i]
            ema20 = ema(closes[:i],20)[-1]
            ema50 = ema(closes[:i],50)[-1]
            rsi_val = rsi(closes[:i])

            risk = calculate_risk(price, ema20, ema50, rsi_val)

            # ===== OPEN =====
            if risk >= 3 and balance >= TRADE_SIZE and len(open_trades) < 5:

                entry = price
                sl = entry * 0.995
                tp = entry * 1.01

                open_trades.append({
                    "symbol": sym,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "time": datetime.utcfromtimestamp(times[i]/1000).isoformat()
                })

                balance -= TRADE_SIZE

            # ===== CLOSE =====
            new_open = []
            for t in open_trades:
                if price >= t["tp"] or (not no_sl and price <= t["sl"]):

                    exit_price = price
                    pnl = (exit_price - t["entry"]) / t["entry"] * TRADE_SIZE

                    fee = TRADE_SIZE * FEE * 2
                    pnl -= fee

                    balance += TRADE_SIZE + pnl

                    date = t["time"].split("T")[0]

                    if date not in history:
                        history[date] = []

                    history[date].append({
                        **t,
                        "close_price": exit_price,
                        "profit": round(pnl,2),
                        "pct": round((pnl/TRADE_SIZE)*100,2)
                    })

                else:
                    new_open.append(t)

            open_trades = new_open

    return history

# ================= GENERATE =================
def generate_history():
    print("⚡ Running 7-day backtest...")

    historyA = run_strategy(no_sl=False)
    historyB = run_strategy(no_sl=True)

    save_json(HISTORY_FILE, {
        "strategyA": historyA,
        "strategyB": historyB
    })

    print("✅ Done")

# ================= LOOP =================
def bot_loop():
    while True:
        update_price()
        save_prices()
        time.sleep(5)

# ================= ROUTES =================
@app.route("/")
def index():
    return send_file("index.html")

@app.route("/history")
def history():
    return jsonify(load_json(HISTORY_FILE))

@app.route("/prices")
def prices():
    return jsonify(load_json(PRICE_FILE))

# ================= START =================
if __name__ == "__main__":
    init_files()
    generate_history()

    threading.Thread(target=bot_loop, daemon=True).start()

    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port)