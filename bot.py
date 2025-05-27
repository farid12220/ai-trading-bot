import os
import time
import uuid
import datetime
import requests

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

SUPABASE_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

POSITIONS = {}
MAX_POSITIONS = 50

def fetch_all_tickers():
    url = f"{ALPACA_BASE_URL}/v2/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        assets = response.json()
        return [asset['symbol'] for asset in assets if asset['tradable']]
    return []

def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data.get("quote", {}).get("ap") or data.get("quote", {}).get("bp")
    return None

def insert_trade(ticker, entry, exit_price, profit):
    payload = {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "entry_price": entry,
        "exit_price": exit_price,
        "profit": profit,
        "result": "WIN" if profit >= 0 else "LOSS",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
    }
    url = f"{SUPABASE_URL}/rest/v1/trades"
    requests.post(url, json=payload, headers=SUPABASE_HEADERS)

def monitor_and_trade(tickers):
    for symbol in tickers:
        if symbol in POSITIONS:
            current_price = fetch_price(symbol)
            if not current_price:
                continue
            position = POSITIONS[symbol]
            entry = position['entry']
            max_seen = position['max']
            change = (current_price - entry) / entry
            POSITIONS[symbol]['max'] = max(current_price, max_seen)
            print(f"{symbol} holding, change: {change:.2%}")

            if change <= -0.005:
                insert_trade(symbol, entry, current_price, current_price - entry)
                del POSITIONS[symbol]
            elif change >= 0.01:
                peak_profit = (max_seen - entry) / entry
                if (max_seen - current_price) / entry >= 0.005:
                    insert_trade(symbol, entry, current_price, current_price - entry)
                    del POSITIONS[symbol]
        elif len(POSITIONS) < MAX_POSITIONS:
            entry_price = fetch_price(symbol)
            if entry_price:
                POSITIONS[symbol] = {"entry": entry_price, "max": entry_price}
                print(f"{symbol}: BOUGHT at {entry_price}")
        time.sleep(0.3)

if __name__ == "__main__":
    print("Starting bot...")
    all_tickers = fetch_all_tickers()
    print(f"Loaded {len(all_tickers)} tradable tickers from Alpaca")

    while True:
        monitor_and_trade(all_tickers)
        time.sleep(10)
