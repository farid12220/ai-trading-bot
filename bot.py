import os
import requests
import time
import uuid
import datetime
import random

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
ALPACA_DATA_URL = os.environ.get("ALPACA_DATA_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
TRADE_INTERVAL = 5
MAX_OPEN_POSITIONS = 50
DAILY_LOSS_CAP = -100
DELAY = 0.3

ALL_TICKERS = []
POSITIONS = {}
DAILY_PNL = 0

# === Helper Functions ===
def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    response = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if response.status_code == 200:
        data = response.json()
        return data["quote"].get("ap"), data["quote"].get("bp")
    else:
        print(f"Error fetching price for {symbol}: {response.text}")
        return None, None

def fetch_previous_price(symbol):
    end = datetime.datetime.now()
    start = end - datetime.timedelta(minutes=15)
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?start={start.isoformat()}&end={end.isoformat()}&timeframe=1Min"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        bars = r.json().get("bars", [])
        if len(bars) > 0:
            return bars[0]["o"]  # opening price of 15-min window
    return None

def fetch_volume(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?timeframe=1Day&limit=2"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        bars = r.json().get("bars", [])
        if len(bars) >= 2:
            avg_volume = (bars[0]["v"] + bars[1]["v"]) / 2
            return bars[-1]["v"], avg_volume
    return None, None

def insert_trade(ticker, entry, exit, profit):
    global DAILY_PNL
    DAILY_PNL += profit
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

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        ALL_TICKERS = [asset['symbol'] for asset in data if asset['tradable'] and asset['exchange'] in ["NASDAQ", "NYSE"]]
        print(f"Loaded {len(ALL_TICKERS)} tradable tickers from Alpaca.")
    else:
        print("Failed to load tickers from Alpaca:", response.text)

def simulate_trade():
    global POSITIONS
    if DAILY_PNL <= DAILY_LOSS_CAP:
        print("Daily loss cap reached. Pausing trading.")
        return

    for ticker in list(POSITIONS):
        position = POSITIONS[ticker]
        current_price, _ = fetch_price(ticker)
        if not current_price:
            continue

        entry_price = position['entry_price']
        percent_change = (current_price - entry_price) / entry_price

        if percent_change >= 0.005 and not position.get("breakeven_triggered"):
            position["stop_price"] = entry_price  # break-even stop
            position["breakeven_triggered"] = True

        if percent_change < 0:
            position['cumulative_loss'] += abs(percent_change)

        if position['cumulative_loss'] >= 0.005:
            sell = True
            reason = "Cumulative stop loss triggered"
        elif percent_change <= -0.005 and not position.get("stop_price"):
            sell = True
            reason = "Stop loss"
        elif position.get("stop_price") and current_price <= position["stop_price"]:
            sell = True
            reason = "Break-even stop triggered"
        else:
            sell = False
            reason = None

        if sell:
            profit = current_price - entry_price
            insert_trade(ticker, entry_price, current_price, profit)
            print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f} | {reason}")
            del POSITIONS[ticker]
        else:
            print(f"{ticker} holding, change: {percent_change*100:.2f}%")
        time.sleep(DELAY)

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue

        prev_price = fetch_previous_price(ticker)
        current_price, _ = fetch_price(ticker)
        current_vol, avg_vol = fetch_volume(ticker)

        if not prev_price or not current_price or not current_vol or not avg_vol:
            continue

        if current_price < prev_price * 1.02:
            continue  # momentum filter fail

        if current_vol < avg_vol:
            continue  # volume filter fail

        POSITIONS[ticker] = {
            'entry_price': current_price,
            'last_price': current_price,
            'trail_active': False,
            'peak_price': current_price,
            'cumulative_loss': 0,
            'breakeven_triggered': False,
            'stop_price': None
        }
        print(f"{ticker}: BOUGHT at {current_price:.2f}")
        time.sleep(DELAY)

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
