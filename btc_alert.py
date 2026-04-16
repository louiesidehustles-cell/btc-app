<<<<<<< HEAD


import requests
from datetime import datetime
import json
import os
import time
from flask import Flask, send_from_directory, jsonify

# ================= SETTINGS =================
BOT_TOKEN = "8767783737:AAF6h6jdaxelJgxgcd72PecIhCfTQBxHfOE"
CHAT_ID = "-5296624289"

# ================= TELEGRAM =================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        print("Telegram error")

# ================= FILE PATH (Fly storage) =================
DATA_FILE = "/data/data.json"
HISTORY_FILE = "/data/history.json"
PRICES_FILE = "/data/prices.json"

# ================= INIT FILES =================
def init_files():
    # 🔥 CREATE FOLDER FIRST
    os.makedirs("/data", exist_ok=True)

    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"open_trades": []}, f)

    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            json.dump({}, f)

    if not os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, "w") as f:
            json.dump([], f)

# ================= LOAD / SAVE =================
def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_history():
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)

def save_history(hist):
    with open(HISTORY_FILE, "w") as f:
        json.dump(hist, f, indent=2)

# ================= PRICE =================
price_cache = {}
prev_price_cache = {}

def update_price_cache():
    global price_cache, prev_price_cache
    try:
        data = requests.get("https://api.binance.com/api/v3/ticker/price").json()
        prev_price_cache = price_cache.copy()
        price_cache = {x["symbol"]: float(x["price"]) for x in data}
    except:
        pass

def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","ADAUSDT","DOGEUSDT"]

    data = []
    for sym in symbols:
        if sym in price_cache:
            data.append({
                "symbol": sym,
                "price": price_cache[sym]
            })

    with open(PRICES_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ================= SIGNAL =================
last_signal_time = 0

def check_signal():
    global last_signal_time

    now = time.time()
    if now - last_signal_time < 15:
        return

    last_signal_time = now
    data = load_data()

    SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","ADAUSDT","DOGEUSDT"]

    for sym in SYMBOLS:
        price = price_cache.get(sym)
        prev = prev_price_cache.get(sym)

        if not price or not prev:
            continue

        if price > prev * 1.004:  # stronger momentum
            entry = price
            sl = round(entry * 0.995, 2)
            tp = round(entry * 1.015, 2)

            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": sym,
                "dir": "BUY",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "status": "OPEN",
                "profit": "",
                "pct": ""
            }

            data["open_trades"].append(trade)
            save_data(data)

            send_telegram(f"📈 {sym} BUY\nEntry: {entry}\nSL: {sl}\nTP: {tp}")
            print("Signal:", sym)
            break

# ================= CLOSE TRADES =================
def check_close_trades():
    data = load_data()
    history = load_history()

    updated = []

    for t in data["open_trades"]:
        price = price_cache.get(t["symbol"])
        if not price:
            updated.append(t)
            continue

        entry = float(t["entry"])

        if price >= float(t["tp"]):
            t["status"] = "WIN"
            profit = price - entry
        elif price <= float(t["sl"]):
            t["status"] = "LOSS"
            profit = price - entry
        else:
            updated.append(t)
            continue

        pct = (profit / entry) * 100
        t["profit"] = round(profit, 2)
        t["pct"] = round(pct, 2)

        date = t["time"].split(" ")[0]

        if date not in history:
            history[date] = []

        history[date].append(t)

    data["open_trades"] = updated
    save_data(data)
    save_history(history)

# ================= BOT LOOP =================
def bot_loop():
    while True:
        try:
            update_price_cache()
            save_prices()
            check_signal()
            check_close_trades()
            print("Running...", datetime.now())
            time.sleep(5)
        except Exception as e:
            print("Error:", e)
            send_telegram(f"⚠️ Bot Error: {e}")
            time.sleep(10)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/data")
def get_data():
    return jsonify(load_data())

@app.route("/history")
def get_history():
    return jsonify(load_history())

@app.route("/prices")
def get_prices():
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE) as f:
            return jsonify(json.load(f))
    return jsonify([])

# ================= START =================
init_files()

import threading
threading.Thread(target=bot_loop, daemon=True).start()

=======


import requests
from datetime import datetime
import json
import os
import time
from flask import Flask, send_from_directory, jsonify

# ================= SETTINGS =================
BOT_TOKEN = "8767783737:AAF6h6jdaxelJgxgcd72PecIhCfTQBxHfOE"
CHAT_ID = "-5296624289"

# ================= TELEGRAM =================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        print("Telegram error")

# ================= FILE PATH (Fly storage) =================
DATA_FILE = "/data/data.json"
HISTORY_FILE = "/data/history.json"
PRICES_FILE = "/data/prices.json"

# ================= INIT FILES =================
def init_files():
    # 🔥 CREATE FOLDER FIRST
    os.makedirs("/data", exist_ok=True)

    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"open_trades": []}, f)

    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            json.dump({}, f)

    if not os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, "w") as f:
            json.dump([], f)

# ================= LOAD / SAVE =================
def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_history():
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)

def save_history(hist):
    with open(HISTORY_FILE, "w") as f:
        json.dump(hist, f, indent=2)

# ================= PRICE =================
price_cache = {}
prev_price_cache = {}

def update_price_cache():
    global price_cache, prev_price_cache
    try:
        data = requests.get("https://api.binance.com/api/v3/ticker/price").json()
        prev_price_cache = price_cache.copy()
        price_cache = {x["symbol"]: float(x["price"]) for x in data}
    except:
        pass

def save_prices():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","ADAUSDT","DOGEUSDT"]

    data = []
    for sym in symbols:
        if sym in price_cache:
            data.append({
                "symbol": sym,
                "price": price_cache[sym]
            })

    with open(PRICES_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ================= SIGNAL =================
last_signal_time = 0

def check_signal():
    global last_signal_time

    now = time.time()
    if now - last_signal_time < 15:
        return

    last_signal_time = now
    data = load_data()

    SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","ADAUSDT","DOGEUSDT"]

    for sym in SYMBOLS:
        price = price_cache.get(sym)
        prev = prev_price_cache.get(sym)

        if not price or not prev:
            continue

        if price > prev * 1.004:  # stronger momentum
            entry = price
            sl = round(entry * 0.995, 2)
            tp = round(entry * 1.015, 2)

            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": sym,
                "dir": "BUY",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "status": "OPEN",
                "profit": "",
                "pct": ""
            }

            data["open_trades"].append(trade)
            save_data(data)

            send_telegram(f"📈 {sym} BUY\nEntry: {entry}\nSL: {sl}\nTP: {tp}")
            print("Signal:", sym)
            break

# ================= CLOSE TRADES =================
def check_close_trades():
    data = load_data()
    history = load_history()

    updated = []

    for t in data["open_trades"]:
        price = price_cache.get(t["symbol"])
        if not price:
            updated.append(t)
            continue

        entry = float(t["entry"])

        if price >= float(t["tp"]):
            t["status"] = "WIN"
            profit = price - entry
        elif price <= float(t["sl"]):
            t["status"] = "LOSS"
            profit = price - entry
        else:
            updated.append(t)
            continue

        pct = (profit / entry) * 100
        t["profit"] = round(profit, 2)
        t["pct"] = round(pct, 2)

        date = t["time"].split(" ")[0]

        if date not in history:
            history[date] = []

        history[date].append(t)

    data["open_trades"] = updated
    save_data(data)
    save_history(history)

# ================= BOT LOOP =================
def bot_loop():
    while True:
        try:
            update_price_cache()
            save_prices()
            check_signal()
            check_close_trades()
            print("Running...", datetime.now())
            time.sleep(5)
        except Exception as e:
            print("Error:", e)
            send_telegram(f"⚠️ Bot Error: {e}")
            time.sleep(10)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/data")
def get_data():
    return jsonify(load_data())

@app.route("/history")
def get_history():
    return jsonify(load_history())

@app.route("/prices")
def get_prices():
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE) as f:
            return jsonify(json.load(f))
    return jsonify([])

# ================= START =================
init_files()

import threading
threading.Thread(target=bot_loop, daemon=True).start()

>>>>>>> 47b7d13 (add auto deploy)
app.run(host="0.0.0.0", port=8080)