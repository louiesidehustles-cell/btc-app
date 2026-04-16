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

price_cache = {}
last_candle = None

# ================= INIT =================
def init_files():
    os.makedirs(BASE_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        json.dump({"open_trades": []}, open(DATA_FILE, "w"))

    if not os.path.exists(HISTORY_FILE):
        json.dump({}, open(HISTORY_FILE, "w"))

    if not os.path.exists(PRICE_FILE):
        json.dump([], open(PRICE_FILE, "w"))

# ================= HELPERS =================
def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {} if "history" in path else {"open_trades": []}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ================= PRICE =================
def update_price():
    global price_cache
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5).json()
        price_cache = {x["symbol"]: float(x["price"]) for x in res}
    except:
        pass

def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]
    data = [{"symbol": s, "price": price_cache.get(s, 0)} for s in symbols]
    save_json(PRICE_FILE, data)

# ================= INDICATORS =================
def ema(prices, period):
    k = 2/(period+1)
    ema_vals = [prices[0]]
    for p in prices[1:]:
        ema_vals.append(p*k + ema_vals[-1]*(1-k))
    return ema_vals

def rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff,0))
        losses.append(abs(min(diff,0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100/(1+rs))

# ================= RISK =================
def calculate_risk(price, ema20, ema50, rsi_val):
    score = 1

    if price > ema20 > ema50:
        score += 2
    elif price > ema20:
        score += 1

    if 50 < rsi_val < 65:
        score += 2
    elif rsi_val < 70:
        score += 1

    return min(score,5)

# ================= SIGNAL =================
def check_signal():
    global last_candle

    now = int(time.time()//300)
    if last_candle == now:
        return
    last_candle = now

    data = load_json(DATA_FILE)

    if len(data["open_trades"]) >= 6:
        return

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]

    for sym in symbols:
        try:
            klines = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": sym, "interval": "5m", "limit": 50}
            ).json()

            closes = [float(k[4]) for k in klines]

            price = closes[-1]
            ema20 = ema(closes,20)[-1]
            ema50 = ema(closes,50)[-1]
            rsi_val = rsi(closes)

            risk = calculate_risk(price, ema20, ema50, rsi_val)

            # ❌ FILTER LOW QUALITY
            if risk < 2:
                continue

            trade = {
                "time": datetime.utcnow().isoformat(),
                "symbol": sym,
                "entry": price,
                "sl": round(price*0.995,4),
                "tp": round(price*1.01,4),
                "risk": risk
            }

            data["open_trades"].append(trade)
            save_json(DATA_FILE, data)

            break
        except:
            continue

# ================= CLOSE =================
def check_close():
    data = load_json(DATA_FILE)
    history = load_json(HISTORY_FILE)

    updated = []

    for t in data["open_trades"]:
        price = price_cache.get(t["symbol"])

        if not price:
            updated.append(t)
            continue

        if price >= t["tp"] or price <= t["sl"]:

            entry = t["entry"]
            pct = (price-entry)/entry

            profit = TRADE_SIZE * pct

            t["profit"] = round(profit,2)
            t["pct"] = round(pct*100,2)

            date = t["time"].split("T")[0]

            if date not in history:
                history[date] = []

            history[date].append(t)

        else:
            updated.append(t)

    data["open_trades"] = updated

    save_json(DATA_FILE, data)
    save_json(HISTORY_FILE, history)

# ================= BACKTEST =================
def generate_backtest():
    history = {}

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]

    for sym in symbols:
        klines = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": sym, "interval": "5m", "limit": 600}
        ).json()

        closes = [float(k[4]) for k in klines]
        times = [k[0] for k in klines]

        trade = None

        for i in range(50,len(closes)):

            price = closes[i]
            ema20 = ema(closes[:i],20)[-1]
            ema50 = ema(closes[:i],50)[-1]
            rsi_val = rsi(closes[:i])

            risk = calculate_risk(price, ema20, ema50, rsi_val)

            if not trade:
                if risk >= 3 and price > ema20:
                    trade = {
                        "symbol": sym,
                        "entry": price,
                        "sl": price*0.995,
                        "tp": price*1.01,
                        "risk": risk,
                        "time": datetime.utcfromtimestamp(times[i]/1000).isoformat()
                    }

            else:
                if price >= trade["tp"] or price <= trade["sl"]:

                    pct = (price-trade["entry"])/trade["entry"]
                    profit = TRADE_SIZE * pct

                    trade["profit"] = round(profit,2)
                    trade["pct"] = round(pct*100,2)

                    date = trade["time"].split("T")[0]

                    if date not in history:
                        history[date] = []

                    history[date].append(trade)

                    trade = None

    save_json(HISTORY_FILE, history)

# ================= BALANCE =================
def calculate_balance():
    history = load_json(HISTORY_FILE)

    balance = START_BALANCE

    for day in history.values():
        for t in day:
            balance += t.get("profit",0)

    return round(balance,2)

# ================= LOOP =================
def bot_loop():
    while True:
        try:
            update_price()
            save_prices()
            check_signal()
            check_close()
        except Exception as e:
            print("ERROR:", e)

        time.sleep(5)

# ================= ROUTES =================
@app.route("/")
def index():
    return send_file("index.html")

@app.route("/data")
def data():
    return jsonify(load_json(DATA_FILE))

@app.route("/history")
def history():
    return jsonify(load_json(HISTORY_FILE))

@app.route("/prices")
def prices():
    return jsonify(load_json(PRICE_FILE))

@app.route("/balance")
def balance():
    return jsonify({"balance": calculate_balance()})

# ================= START =================
if __name__ == "__main__":
    init_files()

    try:
        generate_backtest()
    except Exception as e:
        print("BACKTEST ERROR:", e)

    threading.Thread(target=bot_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)