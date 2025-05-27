import requests
import time
import uuid
import datetime
import os

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
ALPACA_DATA_URL = os.environ.get("ALPACA_DATA_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET
}

# === GLOBAL STATE ===
ALL_TICKERS = []
TOP_PERFORMERS = []
POSITIONS = {}
HOLD_LIMIT = 5
TRADE_INTERVAL = 5

# === LOAD TICKERS ===
def load_all_tickers():
    global ALL_TICKERS
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        print("Missing Alpaca credentials")
        return

    url = f"{ALPACA_BASE_URL}/v2/assets"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            ALL_TICKERS = [d['symbol'] for d in data if d.get('tradable') and d.get('status') == 'active']
            print(f"Loaded {len(ALL_TICKERS)} tickers from Alpaca.")
        else:
            print(f"Failed to load tickers from Alpaca: {response.text}")
    except Exception as e:
        print("Error loading tickers:", str(e))

# === FETCH PRICE ===
def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            return data['quote']['ap']
        else:
            print(f"Error fetching price for {symbol}: {response.text}")
            return None
    except Exception as e:
        print("Fetch error:", str(e))
        return None

# === RECORD TRADE ===
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
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{SUPABASE_URL}/rest/v1/trades"
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code not in [200, 201]:
        print("Error inserting trade:", r.text)

# === TOP STOCKS ===
def update_top_performers():
    global TOP_PERFORMERS
    print("Scanning top-performing stocks...")
    sample = ALL_TICKERS[:100]
    gainers = []
    for symbol in sample:
        price = fetch_price(symbol)
        if price:
            change = random.uniform(-0.05, 0.05)  # Mock gain for now
            gainers.append((symbol, change))
        time.sleep(0.1)
    gainers.sort(key=lambda x: x[1], reverse=True)
    TOP_PERFORMERS = [g[0] for g in gainers[:10]]
    print(f"Top performers: {TOP_PERFORMERS}")

# === SIMULATE TRADES ===
def simulate_trade():
    global POSITIONS
    for ticker in list(POSITIONS):
        current = fetch_price(ticker)
        if not current:
            continue
        if current > POSITIONS[ticker]['last_price']:
            POSITIONS[ticker]['last_price'] = current
            POSITIONS[ticker]['hold_count'] += 1
        else:
            POSITIONS[ticker]['hold_count'] += 1
        if POSITIONS[ticker]['hold_count'] >= HOLD_LIMIT:
            entry = POSITIONS[ticker]['entry_price']
            profit = current - entry
            insert_trade(ticker, entry, current, profit)
            print(f"{ticker}: SOLD at {current}, Profit: {profit:.2f}")
            del POSITIONS[ticker]
    if len(POSITIONS) < 3 and TOP_PERFORMERS:
        ticker = random.choice(TOP_PERFORMERS)
        entry = fetch_price(ticker)
        if entry:
            POSITIONS[ticker] = {
                "entry_price": entry,
                "last_price": entry,
                "hold_count": 0
            }
            print(f"{ticker}: BOUGHT at {entry}")

# === MAIN ===
if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    update_top_performers()
    print("AI Trading bot started...")
    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
        if int(time.time()) % 60 == 0:
            update_top_performers()
