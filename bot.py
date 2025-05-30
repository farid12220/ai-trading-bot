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
DELAY = 0.3
MOMENTUM_WINDOW_MINUTES = 15
MOMENTUM_THRESHOLD = 0.01  # 1%
DAILY_LOSS_LIMIT = -100.0

ALL_TICKERS = []
POSITIONS = {}
DAILY_PROFIT = 0.0


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


def fetch_momentum(symbol):
    end = datetime.datetime.utcnow()
    start = end - datetime.timedelta(minutes=MOMENTUM_WINDOW_MINUTES)
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?start={start.isoformat()}Z&end={end.isoformat()}Z&timeframe=1Min"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    response = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if response.status_code == 200:
        bars = response.json().get("bars", [])
        if len(bars) >= 2:
            open_price = bars[0]["o"]
            close_price = bars[-1]["c"]
            volume_now = bars[-1]["v"]
            avg_volume = sum(b["v"] for b in bars) / len(bars)
            momentum = (close_price - open_price) / open_price
            return momentum, volume_now, avg_volume
    return None, 0, 1


def insert_trade(ticker, entry, exit, profit):
    global DAILY_PROFIT
    DAILY_PROFIT += profit
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
    global POSITIONS, DAILY_PROFIT

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

        if percent_change <= -0.005 and not position.get('break_even'):
            sell = position['cumulative_loss'] >= 0.005
            reason = "Cumulative stop loss triggered" if sell else None
        elif position.get('break_even') and percent_change <= 0:
            sell = True
            reason = "Break-even stop triggered"
        elif percent_change >= 0.01:
            if not position['trail_active']:
                position['trail_active'] = True
                position['peak_price'] = current_price
            else:
                position['peak_price'] = max(position['peak_price'], current_price)
            sell = False
            reason = None
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
            print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f} ({percent_change*100:.2f}%) | {reason}")
            del POSITIONS[ticker]
        else:
            print(f"{ticker} holding, change: {percent_change*100:.2f}%")
        time.sleep(DELAY)

    if DAILY_PROFIT <= DAILY_LOSS_LIMIT:
        print("Daily loss limit reached. Halting trading.")
        return

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue

        momentum, vol_now, vol_avg = fetch_momentum(ticker)
        if momentum is None or momentum < MOMENTUM_THRESHOLD or vol_now < vol_avg:
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
