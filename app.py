from flask import Flask, jsonify, send_file, request
import requests, json, os, threading, time
from datetime import datetime
import pytz

app = Flask(__name__)

# ===== PATHS =====
BASE_DIR = "/data"
DATA_FILE = f"{BASE_DIR}/data.json"
HISTORY_FILE = f"{BASE_DIR}/history.json"
PRICE_FILE = f"{BASE_DIR}/prices.json"
USERS_FILE = f"{BASE_DIR}/users.json"

# ===== GLOBALS =====
price_cache = {}
last_trade_time = {}
last_candle_time = None

# ===== INIT FILES =====
def init_files():
    os.makedirs(BASE_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        json.dump({"open_trades": []}, open(DATA_FILE, "w"))

    if not os.path.exists(HISTORY_FILE):
        json.dump({}, open(HISTORY_FILE, "w"))

    if not os.path.exists(PRICE_FILE):
        json.dump([], open(PRICE_FILE, "w"))

    if not os.path.exists(USERS_FILE):
        json.dump({}, open(USERS_FILE, "w"))

# ===== JSON HELPERS =====
def load_json(path):
    try:
        if not os.path.exists(path):
            return {} if "history" in path or "users" in path else {"open_trades": []}
        with open(path) as f:
            return json.load(f)
    except:
        return {} if "history" in path or "users" in path else {"open_trades": []}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ===== PRICE =====
def update_price():
    global price_cache
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5).json()
        price_cache = {x["symbol"]: float(x["price"]) for x in res}
    except Exception as e:
        print("PRICE ERROR:", e)

def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","CFXUSDT"]
    data = [{"symbol": s, "price": price_cache.get(s, 0)} for s in symbols]
    save_json(PRICE_FILE, data)

# ===== INDICATORS =====
def get_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "5m", "limit": 50}
    return requests.get(url, params=params).json()

def ema(prices, period):
    k = 2 / (period + 1)
    ema_vals = [prices[0]]
    for p in prices[1:]:
        ema_vals.append(p * k + ema_vals[-1] * (1 - k))
    return ema_vals

def rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ===== RISK =====
def calculate_risk(price, ema20, ema50, rsi_val):
    score = 0

    if price > ema20 > ema50:
        score += 2
    elif price > ema20:
        score += 1

    if 50 < rsi_val < 65:
        score += 2
    elif rsi_val < 70:
        score += 1

    return max(1, min(5, score))

# ===== NEW CANDLE =====
def is_new_candle(interval=300):
    global last_candle_time
    now = int(time.time() // interval)
    if last_candle_time == now:
        return False
    last_candle_time = now
    return True

# ===== SIGNAL =====
def check_signal():
    if not is_new_candle():
        return

    data = load_json(DATA_FILE)

    if len(data["open_trades"]) >= 6:
        return

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","CFXUSDT"]

    for sym in symbols:

        now = time.time()
        if sym in last_trade_time and now - last_trade_time[sym] < 180:
            continue

        klines = get_klines(sym)
        closes = [float(k[4]) for k in klines]

        price = closes[-1]
        ema20 = ema(closes, 20)[-1]
        ema50 = ema(closes, 50)[-1]
        rsi_val = rsi(closes)

        risk = calculate_risk(price, ema20, ema50, rsi_val)

        entry = price
        sl = round(entry * 0.995, 4)
        tp = round(entry * 1.01, 4)

        trade = {
            "user": "demo",
            "time": datetime.utcnow().isoformat(),
            "symbol": sym,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk": risk
        }

        data["open_trades"].append(trade)
        save_json(DATA_FILE, data)

        last_trade_time[sym] = now

        print(f"NEW TRADE {sym} risk {risk}")
        break

# ===== CLOSE =====
def check_close():
    data = load_json(DATA_FILE)
    history = load_json(HISTORY_FILE)

    updated = []

    for t in data["open_trades"]:
        price = price_cache.get(t["symbol"])

        if not price:
            updated.append(t)
            continue

        entry = t["entry"]

        if price >= t["tp"] or price <= t["sl"]:
            profit = price - entry
            pct = (profit / entry) * 100

            t["profit"] = round(profit, 2)
            t["pct"] = round(pct, 2)

            date = t["time"].split("T")[0]

            if date not in history:
                history[date] = []

            history[date].append(t)
        else:
            updated.append(t)

    data["open_trades"] = updated

    save_json(DATA_FILE, data)
    save_json(HISTORY_FILE, history)

def generate_backtest_history(days=2):
    print("⚡ Generating backtest history...")

    history = {}

    symbols = ["BTCUSDT","ETHUSDT","SOLUSDT"]

    for sym in symbols:

        klines = get_klines(sym, "5m", 600)  # ~2 days

        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        times = [k[0] for k in klines]

        open_trade = None

        for i in range(50, len(closes)):

            price = closes[i]

            ema20 = calculate_ema(closes[:i], 20)[-1]
            ema50 = calculate_ema(closes[:i], 50)[-1]
            rsi = calculate_rsi(closes[:i])

            avg_vol = sum(volumes[i-10:i]) / 10
            current_vol = volumes[i]

            volatility = get_volatility(closes[:i])
            cfg = get_dynamic_thresholds(volatility)

            risk = calculate_risk(price, ema20, ema50, rsi, current_vol, avg_vol)

            # ===== OPEN TRADE =====
            if not open_trade:

                if risk >= 3 and price > ema20 and rsi < cfg["rsi_high"]:
                    
                    entry = price
                    sl = entry * (1 - cfg["sl"])
                    tp = entry * (1 + cfg["tp"])

                    open_trade = {
                        "symbol": sym,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "risk": risk,
                        "time": datetime.utcfromtimestamp(times[i]/1000).isoformat()
                    }

            # ===== CLOSE TRADE =====
            elif open_trade:

                if price >= open_trade["tp"] or price <= open_trade["sl"]:

                    profit = price - open_trade["entry"]
                    pct = (profit / open_trade["entry"]) * 100

                    date = open_trade["time"].split("T")[0]

                    trade = {
                        **open_trade,
                        "close_price": price,
                        "profit": round(profit, 2),
                        "pct": round(pct, 2)
                    }

                    if date not in history:
                        history[date] = []

                    history[date].append(trade)

                    open_trade = None

    save_json(HISTORY_FILE, history)

    print("✅ Backtest complete")



# ===== LOOP =====
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

# ===== ROUTES =====
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

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    users = load_json(USERS_FILE)

    if data["username"] in users:
        return jsonify({"error":"exists"}), 400

    users[data["username"]] = {
        "password": data["password"],
        "balance": 1000
    }

    save_json(USERS_FILE, users)
    return jsonify({"ok":True})

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    users = load_json(USERS_FILE)

    if data["username"] not in users:
        return jsonify({"error":"no user"}), 400

    if users[data["username"]]["password"] != data["password"]:
        return jsonify({"error":"wrong"}), 400

    return jsonify({"ok":True})

# ===== START =====
if __name__ == "__main__":
    init_files()

    # 🔥 RESET HISTORY + GENERATE REAL BACKTEST
    generate_backtest_history(days=2)

    threading.Thread(target=bot_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)