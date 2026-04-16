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
FEE = 0.001

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

#======= Live Trading =======
def run_live_trading():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]

    while True:
        data = load_json(DATA_FILE)
        open_trades = data.get("open_trades", [])

        for sym in symbols:
            try:
                klines = get_7d_klines(sym)[-100:]
                closes = [float(k[4]) for k in klines]

                price = closes[-1]
                ema20_val = ema(closes,20)[-1]
                ema50_val = ema(closes,50)[-1]
                rsi_val = rsi(closes)

                risk = calculate_risk(price, ema20_val, ema50_val, rsi_val)

                # ===== OPEN TRADE =====
                if risk >= 3 and len(open_trades) < 10:
                    entry = price

                    trade = {
                        "symbol": sym,
                        "entry": entry,
                        "sl": entry * 0.995,
                        "tp": entry * 1.01,
                        "risk": risk,
                        "time": datetime.utcnow().isoformat()
                    }

                    open_trades.append(trade)

            except:
                continue

        # ===== CLOSE TRADES =====
        new_open = []

        for t in open_trades:
            current = price_cache.get(t["symbol"], t["entry"])

            if current >= t["tp"] or current <= t["sl"]:
                # closed → ignore for now (can log later)
                continue
            else:
                new_open.append(t)

        data["open_trades"] = new_open
        save_json(DATA_FILE, data)

        time.sleep(10)

# ================= FETCH =================
def get_7d_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"
    all_data = []
    end = int(time.time()*1000)

    for _ in range(3):
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

    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]

    # 🔥 merge ALL candles into ONE timeline
    all_candles = []

    for sym in symbols:
        klines = get_7d_klines(sym)
        for k in klines:
            all_candles.append({
                "symbol": sym,
                "time": k[0],
                "close": float(k[4])
            })

    # sort by time (IMPORTANT)
    all_candles.sort(key=lambda x: x["time"])

    balance = START_BALANCE
    open_trades = []
    history = {}

    price_history = {s: [] for s in symbols}

    for c in all_candles:

        sym = c["symbol"]
        price = c["close"]
        time_ts = c["time"]

        price_history[sym].append(price)

        if len(price_history[sym]) < 50:
            continue

        closes = price_history[sym]

        ema20 = ema(closes,20)[-1]
        ema50 = ema(closes,50)[-1]
        rsi_val = rsi(closes)

        risk = calculate_risk(price, ema20, ema50, rsi_val)

        # ===== CLOSE FIRST =====
        new_open = []
        for t in open_trades:

            if t["symbol"] != sym:
                new_open.append(t)
                continue

            if price >= t["tp"] or (not no_sl and price <= t["sl"]):

                pnl = (price - t["entry"]) / t["entry"] * TRADE_SIZE
                fee = TRADE_SIZE * FEE * 2
                pnl -= fee

                balance += TRADE_SIZE + pnl

                date = t["time"].split("T")[0]

                if date not in history:
                    history[date] = []

                history[date].append({
                    **t,
                    "close_price": price,
                    "profit": round(pnl,2),
                    "pct": round((pnl/TRADE_SIZE)*100,2)
                })

            else:
                new_open.append(t)

        open_trades = new_open

        # ===== OPEN AFTER CLOSE =====
        if risk >= 3 and balance >= TRADE_SIZE:

            entry = price
            sl = entry * 0.995
            tp = entry * 1.01

            open_trades.append({
                "symbol": sym,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "time": datetime.utcfromtimestamp(time_ts/1000).isoformat()
            })

            balance -= TRADE_SIZE

    return history
#=========== GENERATE SIGNALS ========
def generate_signals():
    symbols = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","CFXUSDT"]

    signals = []

    for sym in symbols:
        try:
            klines = get_7d_klines(sym)[-100:]  # last candles only
            closes = [float(k[4]) for k in klines]

            if len(closes) < 50:
                continue

            price = closes[-1]
            ema20_val = ema(closes, 20)[-1]
            ema50_val = ema(closes, 50)[-1]
            rsi_val = rsi(closes)

            risk = calculate_risk(price, ema20_val, ema50_val, rsi_val)

            if risk >= 3:  # only show decent signals
                signals.append({
                    "symbol": sym,
                    "entry": round(price, 4),
                    "tp": round(price * 1.01, 4),
                    "sl": round(price * 0.995, 4),
                    "risk": risk,
                    "time": datetime.utcnow().isoformat()
                })

        except Exception as e:
            print("Signal error:", sym, e)

    save_json(DATA_FILE, {"open_trades": signals})


# ================= GENERATE =================
def generate_history():
    print("⚡ Running 7-day REAL simulation...")

    historyA = run_strategy(no_sl=False)
    historyB = run_strategy(no_sl=True)

    save_json(HISTORY_FILE, {
        "strategyA": historyA,
        "strategyB": historyB
    })

    print("✅ Done")

#=============== safe generate ======
def safe_generate():
    try:
        print("⚡ Background backtest started...")
        generate_history()
        print("✅ Backtest done")
    except Exception as e:
        print("❌ BACKTEST ERROR:", str(e))

# ================= LOOP =================
def bot_loop():
    while True:
        update_price()
        save_prices()
        generate_signals()  
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

@app.route("/generate")
def generate():
    threading.Thread(target=safe_generate, daemon=True).start()
    return {"status": "started"}

@app.route("/data")
def data():
    return jsonify(load_json(DATA_FILE))

# ================= START =================
if __name__ == "__main__":
    init_files()

    threading.Thread(target=run_live_trading, daemon=True).start()
     # ✅ run in background (does NOT block server)
    threading.Thread(target=safe_generate, daemon=True).start()

    threading.Thread(target=bot_loop, daemon=True).start()

    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port)