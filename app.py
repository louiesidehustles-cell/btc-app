from flask import Flask, jsonify, send_file
import requests, json, os, threading, time
from datetime import datetime
import pytz
import time

app = Flask(__name__)
last_summary_date = None
last_trade_time = {}
last_candle_time = None


# ===== TELEGRAM =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    try:
        if not BOT_TOKEN or not CHAT_ID:
            return

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": msg
        }, timeout=5)

    except Exception as e:
        print("TELEGRAM ERROR:", e)


# ===== FILES =====
BASE_DIR = "/data"
DATA_FILE = f"{BASE_DIR}/data.json"
HISTORY_FILE = f"{BASE_DIR}/history.json"
PRICE_FILE = f"{BASE_DIR}/prices.json"

price_cache = {}
prev_price_cache = {}
last_signal_time = 0


# ===== INIT =====
def init_files():
    os.makedirs(BASE_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        json.dump({"open_trades": []}, open(DATA_FILE, "w"))

    if not os.path.exists(HISTORY_FILE):
        json.dump({}, open(HISTORY_FILE, "w"))

    if not os.path.exists(PRICE_FILE):
        json.dump([], open(PRICE_FILE, "w"))


def load_json(path):
    if not os.path.exists(path):
        return {} if "history" in path else {"open_trades": []}

    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print("JSON LOAD ERROR:", e)
        return {} if "history" in path else {"open_trades": []}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ===== PRICE =====
def update_price():
    global price_cache, prev_price_cache
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5).json()
        prev_price_cache = price_cache.copy()
        price_cache = {x["symbol"]: float(x["price"]) for x in res}
    except Exception as e:
        print("PRICE ERROR:", e)


def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","CFXUSDT"]
    data = [{"symbol": s, "price": price_cache.get(s, 0)} for s in symbols]
    save_json(PRICE_FILE, data)


# ===== RISK =====
def get_risk_level(price, prev):
    if not price or not prev:
        return None

    change = abs((price - prev) / prev)

    if change > 0.0005: return 5
    elif change > 0.0004: return 4
    elif change > 0.0003: return 3
    elif change > 0.0002: return 2
    elif change > 0.0001: return 1

    return None


# ===== SIGNAL =====

def check_signal():
    global last_signal_time

    now = time.time()

    # ✅ only trigger on new candle (5m)
    if not is_new_candle(300):
        return

    data = load_json(DATA_FILE)

    if len(data["open_trades"]) >= 10:
        return

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","CFXUSDT"]


    for sym in symbols:

        # 🧠 cooldown per symbol
        if sym in last_trade_time:
            if now - last_trade_time[sym] < 300:
                continue

        klines = get_klines(sym, "5m", 50)

        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        price = closes[-1]

        ema20 = calculate_ema(closes, 20)[-1]
        ema50 = calculate_ema(closes, 50)[-1]
        rsi = calculate_rsi(closes)

        avg_vol = sum(volumes[-10:]) / 10
        current_vol = volumes[-1]

        # ===== STRATEGY =====

        # ===== STRATEGY =====

        if not (price > ema20 > ema50):
            continue

        if rsi >= 65:
            continue

        if current_vol <= avg_vol:
            continue

        direction = "BUY"

        entry = price

        if direction == "BUY":
            sl = round(entry * 0.995, 2)
            tp = round(entry * 1.01, 2)
        else:
            sl = round(entry * 1.005, 2)
            tp = round(entry * 0.99, 2)

        trade = {
            "time": datetime.utcnow().isoformat(),
            "symbol": sym,
            "dir": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "status": "OPEN",
            "profit": "",
            "pct": "",
            "risk": 3
        }

        data["open_trades"].append(trade)
        save_json(DATA_FILE, data)

        send_telegram(
            f"{direction} {sym}\nEntry: {entry}\nSL: {sl}\nTP: {tp}"
        )

        last_trade_time[sym] = now
        last_signal_time = now

        print("NEW SIGNAL:", sym, direction)

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

        entry = float(t["entry"])

        if price >= float(t["tp"]) or price <= float(t["sl"]):

            profit = price - entry
            pct = (profit / entry) * 100

            # ✅ freeze values
            t["close_price"] = price
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


#===== DAILY SUMMARY ======
def send_daily_summary():
    global last_summary_date

    syd = pytz.timezone("Australia/Sydney")
    now = datetime.now(syd)

    today = now.strftime("%Y-%m-%d")

    # 🎯 4PM Sydney window
    if now.hour != 16 or now.minute > 15:
        return

    # 🚫 prevent duplicate
    if last_summary_date == today:
        return

    history = load_json(HISTORY_FILE)

    if today not in history:
        return

    trades = history[today]

    # ✅ calculate stats
    wins = sum(1 for t in trades if t.get("profit", 0) > 0)
    losses = sum(1 for t in trades if t.get("profit", 0) <= 0)
    total = sum(t.get("profit", 0) for t in trades)

    # optional win rate
    winrate = (wins / len(trades) * 100) if trades else 0

    send_telegram(
        f"📊 DAILY SUMMARY ({today})\n"
        f"Trades: {len(trades)}\n"
        f"✅ Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"🎯 Winrate: {winrate:.1f}%\n"
        f"💰 PnL: {round(total,2)}"
    )

    last_summary_date = today


#======== FULL STRATEGY ============ 

def is_new_candle(interval=300):
    global last_candle_time

    now = int(time.time() // interval)

    if last_candle_time == now:
        return False

    last_candle_time = now
    return True

def get_klines(symbol, interval="5m", limit=50):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    return requests.get(url, params=params).json()

def calculate_ema(prices, period=20):
    ema = []
    k = 2 / (period + 1)

    for i, price in enumerate(prices):
        if i == 0:
            ema.append(price)
        else:
            ema.append(price * k + ema[i-1] * (1 - k))

    return ema

def calculate_rsi(prices, period=14):
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



# ===== LOOP =====
def bot_loop():
    while True:
        try:
            update_price()
            save_prices()
            check_signal()
            check_close()
            send_daily_summary()
        except Exception as e:
            print("LOOP ERROR:", e)

        time.sleep(5)   # ✅ keep UI responsive


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


# ===== START =====
if __name__ == "__main__":
    init_files()

    threading.Thread(target=bot_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 8080))



app = Flask(__name__)
last_summary_date = None
last_trade_time = {}
last_candle_time = None


# ===== TELEGRAM =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    try:
        if not BOT_TOKEN or not CHAT_ID:
            return

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": msg
        }, timeout=5)

    except Exception as e:
        print("TELEGRAM ERROR:", e)


# ===== FILES =====
BASE_DIR = "/data"
DATA_FILE = f"{BASE_DIR}/data.json"
HISTORY_FILE = f"{BASE_DIR}/history.json"
PRICE_FILE = f"{BASE_DIR}/prices.json"

price_cache = {}
prev_price_cache = {}
last_signal_time = 0


# ===== INIT =====
def init_files():
    os.makedirs(BASE_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        json.dump({"open_trades": []}, open(DATA_FILE, "w"))

    if not os.path.exists(HISTORY_FILE):
        json.dump({}, open(HISTORY_FILE, "w"))

    if not os.path.exists(PRICE_FILE):
        json.dump([], open(PRICE_FILE, "w"))


def load_json(path):
    if not os.path.exists(path):
        return {} if "history" in path else {"open_trades": []}

    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print("JSON LOAD ERROR:", e)
        return {} if "history" in path else {"open_trades": []}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ===== PRICE =====
def update_price():
    global price_cache, prev_price_cache
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5).json()
        prev_price_cache = price_cache.copy()
        price_cache = {x["symbol"]: float(x["price"]) for x in res}
    except Exception as e:
        print("PRICE ERROR:", e)


def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","CFXUSDT"]
    data = [{"symbol": s, "price": price_cache.get(s, 0)} for s in symbols]
    save_json(PRICE_FILE, data)


# ===== RISK =====
def get_risk_level(price, prev):
    if not price or not prev:
        return None

    change = abs((price - prev) / prev)

    if change > 0.0005: return 5
    elif change > 0.0004: return 4
    elif change > 0.0003: return 3
    elif change > 0.0002: return 2
    elif change > 0.0001: return 1

    return None


# ===== SIGNAL =====

def check_signal():
    global last_signal_time

    now = time.time()

    # ✅ only trigger on new candle
    if not is_new_candle(300):   # 5m candles
        return

    data = load_json(DATA_FILE)

    if len(data["open_trades"]) >= 5:
        return  # limit trades

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","CFXUSDT"]


    for sym in symbols:

        # 🧠 cooldown per symbol
        if sym in last_trade_time:
            if now - last_trade_time[sym] < 300:
                continue

        klines = get_klines(sym, "5m", 50)

        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        price = closes[-1]

        ema20 = calculate_ema(closes, 20)[-1]
        ema50 = calculate_ema(closes, 50)[-1]
        rsi = calculate_rsi(closes)

        avg_vol = sum(volumes[-10:]) / 10
        current_vol = volumes[-1]

        # ===== STRATEGY =====

        # ✅ trend filter
        if not (price > ema20 > ema50):
            continue

        # ✅ RSI filter (avoid overbought)
        if rsi >= 70:
            continue

        # ⚠️ TEMP: relax volume filter (or you'll get no signals)
        if current_vol <= avg_vol * 0.9:
            continue

        direction = "BUY"

        # ===== RISK CALCULATION =====
        risk = get_risk_level(price, prev_price_cache.get(sym))

        # ❌ skip if no valid risk
        if risk is None:
            continue

        # ===== TRADE SETUP =====
        entry = price
        sl = round(entry * 0.995, 2)
        tp = round(entry * 1.01, 2)

        trade = {
            "time": datetime.utcnow().isoformat(),
            "symbol": sym,
            "dir": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "status": "OPEN",
            "profit": "",
            "pct": "",
            "risk": risk
        }

        data["open_trades"].append(trade)
        save_json(DATA_FILE, data)

        # ✅ TELEGRAM WITH RISK
        send_telegram(
            f"📈 BUY {sym} (Risk {risk})\n"
            f"Entry: {entry}\nSL: {sl}\nTP: {tp}"
        )

        last_trade_time[sym] = now
        last_signal_time = now

        print(f"NEW SIGNAL: {sym} BUY | Risk {risk}")

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

        entry = float(t["entry"])

        if price >= float(t["tp"]) or price <= float(t["sl"]):

            profit = price - entry
            pct = (profit / entry) * 100

            # ✅ freeze values
            t["close_price"] = price
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


#===== DAILY SUMMARY ======
def send_daily_summary():
    global last_summary_date

    syd = pytz.timezone("Australia/Sydney")
    now = datetime.now(syd)

    today = now.strftime("%Y-%m-%d")

    # 🎯 4PM Sydney window
    if now.hour != 16 or now.minute > 15:
        return

    # 🚫 prevent duplicate
    if last_summary_date == today:
        return

    history = load_json(HISTORY_FILE)

    if today not in history:
        return

    trades = history[today]

    # ✅ calculate stats
    wins = sum(1 for t in trades if t.get("profit", 0) > 0)
    losses = sum(1 for t in trades if t.get("profit", 0) <= 0)
    total = sum(t.get("profit", 0) for t in trades)

    # optional win rate
    winrate = (wins / len(trades) * 100) if trades else 0

    send_telegram(
        f"📊 DAILY SUMMARY ({today})\n"
        f"Trades: {len(trades)}\n"
        f"✅ Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"🎯 Winrate: {winrate:.1f}%\n"
        f"💰 PnL: {round(total,2)}"
    )

    last_summary_date = today


#======== FULL STRATEGY ============ 

def is_new_candle(interval=300):
    global last_candle_time

    now = int(time.time() // interval)

    if last_candle_time == now:
        return False

    last_candle_time = now
    return True

def get_klines(symbol, interval="5m", limit=50):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    return requests.get(url, params=params).json()

def calculate_ema(prices, period=20):
    ema = []
    k = 2 / (period + 1)

    for i, price in enumerate(prices):
        if i == 0:
            ema.append(price)
        else:
            ema.append(price * k + ema[i-1] * (1 - k))

    return ema

def calculate_rsi(prices, period=14):
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



# ===== LOOP =====
def bot_loop():
    while True:
        try:
            update_price()
            save_prices()
            check_signal()
            check_close()
            send_daily_summary()
        except Exception as e:
            print("LOOP ERROR:", e)

        time.sleep(5)   # ✅ keep UI responsive


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


# ===== START =====
if __name__ == "__main__":
    init_files()

    threading.Thread(target=bot_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)