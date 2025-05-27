import requests
import time
import uuid
import datetime
import os

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

if not all([ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL, SUPABASE_URL, SUPABASE_API_KEY]):
    print("❌ Environment variables not set correctly.")
    exit()

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

POSITIONS = {}
ALL_TICKERS = []
TRADE_INTERVAL = 5
STOP_LOSS = 0.005  # 0.5%
TRAILING_PROFIT_TRIGGER = 0.01  # 1%
TRAILING_PROFIT_DROP = 0.005  # 0.5%
MAX_POSITIONS = 50

def load_all_tickers():
    print("🔁 Loading tickers from Alpaca...")
    url = f"{ALPACA_BASE_URL}/v2/assets"
    try:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        assets = r.json()
        tradable = [a['symbol'] for a in assets if a['tradable'] and a['status'] == 'active']
        print(f"✅ Loaded {len(tradable)} tradable tickers from Alpaca")
        return tradable
    except Exception as e:
        print(f"❌ Error loading tickers: {e}")
        return []

def fetch_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    try:
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 429:
            time.sleep(1)
            return None
        r.raise_for_status()
        data = r.json()
        return data['quote']['ap'], True
    except Exception as e:
        print(f"⚠️ Error fetching price for {symbol}: {e}")
        return None, False

def insert_trade(ticker, entry, exit, profit):
    payload = {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "entry_price": entry,
        "exit_price": exit,
        "profit": profit,
        "result": "WIN" if profit >= 0 else "LOSS",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
    }
    r = requests.post(f"{SUPABASE_URL}/rest/v1/trades", json=payload, headers=SUPABASE_HEADERS)
    if r.status_code not in [200, 201]:
        print(f"❌ Error inserting trade for {ticker}: {r.text}")

def scan_stocks():
    global ALL_TICKERS
    selected = []
    for symbol in ALL_TICKERS[:150]:
        price, ok = fetch_price(symbol)
        if ok and price and 1 < price < 500:
            selected.append((symbol, price))
        if len(selected) >= MAX_POSITIONS:
            break
        time.sleep(0.2)
    print(f"🔎 Scanned and selected {len(selected)} tickers.")
    return selected

def simulate_trading_cycle(selected):
    global POSITIONS
    for symbol, price in selected:
        if symbol in POSITIONS:
            position = POSITIONS[symbol]
            change = (price - position['entry']) / position['entry']
            high = position['high']
            if price > high:
                POSITIONS[symbol]['high'] = price

            # stop loss
            if change <= -STOP_LOSS:
                print(f"❌ {symbol} dropped -{change*100:.2f}%, selling.")
                insert_trade(symbol, position['entry'], price, price - position['entry'])
                del POSITIONS[symbol]
                continue

            # trailing profit logic
            gain = (high - position['entry']) / position['entry']
            drop = (high - price) / position['entry']
            if gain >= TRAILING_PROFIT_TRIGGER and drop >= TRAILING_PROFIT_DROP:
                print(f"✅ {symbol} hit trailing target, selling.")
                insert_trade(symbol, position['entry'], price, price - position['entry'])
                del POSITIONS[symbol]
        else:
            if len(POSITIONS) < MAX_POSITIONS:
                POSITIONS[symbol] = {"entry": price, "high": price}
                print(f"🟢 {symbol}: BOUGHT at {price:.2f}")
        time.sleep(0.2)

if __name__ == "__main__":
    print("🚀 Starting bot...")
    ALL_TICKERS = load_all_tickers()
    while True:
        selection = scan_stocks()
        simulate_trading_cycle(selection)
        time.sleep(TRADE_INTERVAL)
