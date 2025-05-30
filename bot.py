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
DAILY_LOSS_LIMIT = -100
DELAY = 0.3

ALL_TICKERS = []
POSITIONS = {}
DAILY_PNL = 0

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

def market_is_open():
    now = datetime.datetime.now().time()
    return now >= datetime.time(9, 30) and now <= datetime.time(16, 0)

def simulate_trade():
    global POSITIONS
    for ticker in list(POSITIONS):
        position = POSITIONS[ticker]
        current_price, _ = fetch_price(ticker)
        if not current_price:
            continue

        entry_price = position['entry_price']
        percent_change = (current_price - entry_price) / entry_price

        if percent_change < 0:
            position['cumulative_loss'] += abs(percent_change)

        if percent_change >= 0.005:
            position['break_even'] = True

        if percent_change >= 0.01:
            position['trail_active'] = True
            position['peak_price'] = max(position['peak_price'], current_price)

        if position['cumulative_loss'] >= 0.005:
            sell = True
            reason = "Cumulative stop loss triggered"
        elif position.get('break_even') and percent_change < 0:
            sell = True
            reason = "Break-even stop triggered"
        elif position['trail_active']:
            drop_from_peak = (position['peak_price'] - current_price) / position['peak_price']
            sell = drop_from_peak >= 0.005
            reason = "Trailing stop hit" if sell else None
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

    if DAILY_PNL <= DAILY_LOSS_LIMIT:
        print("Daily loss cap reached. Pausing trades.")
        return

    if not market_is_open():
        print("Market closed. Skipping buy entries.")
        return

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue
        entry_price, _ = fetch_price(ticker)
        if entry_price:
            POSITIONS[ticker] = {
                'entry_price': entry_price,
                'last_price': entry_price,
                'trail_active': False,
                'peak_price': entry_price,
                'cumulative_loss': 0,
                'break_even': False
            }
            print(f"{ticker}: BOUGHT at {entry_price:.2f}")
        time.sleep(DELAY)

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
