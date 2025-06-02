import os
import requests
import time
import uuid
import datetime
import random
import pytz

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
DAILY_LOSS_CAP = -100
VWAP_TOLERANCE = 0.005  # 0.5%

ALL_TICKERS = []
POSITIONS = {}
DAILY_PROFIT = 0

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

def fetch_vwap(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?timeframe=1Min&limit=20"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if r.status_code != 200:
        return None
    bars = r.json().get("bars", [])
    if not bars:
        return None
    total_vol = sum(b['v'] for b in bars)
    total_vwap = sum((b['h'] + b['l'] + b['c']) / 3 * b['v'] for b in bars)
    return total_vwap / total_vol if total_vol else None

def fetch_recent_candles(symbol, limit=5):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?timeframe=1Min&limit={limit}"
    print(f"Requesting: {url}")
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if r.status_code == 200:
        return r.json().get("bars", [])
    else:
        print(f"Error fetching candles for {symbol}: {r.text}")
        return None

def is_hammer(candle):
    body = abs(candle['c'] - candle['o'])
    lower_wick = candle['o'] - candle['l'] if candle['o'] > candle['c'] else candle['c'] - candle['l']
    upper_wick = candle['h'] - candle['c'] if candle['o'] > candle['c'] else candle['h'] - candle['o']
    return body < (candle['h'] - candle['l']) * 0.3 and lower_wick > body * 2 and upper_wick < body

def is_bullish_engulfing(prev, curr):
    return (
        prev['c'] < prev['o'] and
        curr['c'] > curr['o'] and
        curr['o'] < prev['c'] and
        curr['c'] > prev['o']
    )

def is_marubozu(candle):
    body = abs(candle['c'] - candle['o'])
    total_range = candle['h'] - candle['l']
    upper_wick = candle['h'] - max(candle['c'], candle['o'])
    lower_wick = min(candle['c'], candle['o']) - candle['l']
    return (
        body / total_range > 0.9 and
        upper_wick / total_range < 0.05 and
        lower_wick / total_range < 0.05
    )

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

def market_is_open():
    eastern = pytz.timezone("US/Eastern")
    now_et = datetime.datetime.now(eastern)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, microsecond=0)
    return market_open <= now_et <= market_close

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

        if percent_change >= 0.01:
            if not position['trail_active']:
                position['trail_active'] = True
                position['peak_price'] = current_price
            else:
                position['peak_price'] = max(position['peak_price'], current_price)

        if percent_change >= 0.008 and not position['break_even']:
            position['break_even'] = True

        stop_loss_triggered = position['cumulative_loss'] >= 0.0075
        trailing_stop_triggered = position['trail_active'] and (
            (position['peak_price'] - current_price) / position['peak_price'] >= 0.0075)
        break_even_triggered = position['break_even'] and current_price < entry_price

        sell = stop_loss_triggered or trailing_stop_triggered or break_even_triggered
        reason = "Cumulative stop loss triggered" if stop_loss_triggered else (
            "Trailing stop hit" if trailing_stop_triggered else (
                "Break-even stop hit" if break_even_triggered else None))

        if sell:
            profit = current_price - entry_price
            insert_trade(ticker, entry_price, current_price, profit)
            print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f} ({percent_change*100:.2f}%) | {reason}")
            del POSITIONS[ticker]
        else:
            print(f"{ticker} holding, change: {percent_change*100:.2f}%")
        time.sleep(DELAY)

    if not market_is_open():
        print("Market closed. Skipping buy entries.")
        return

    if DAILY_PROFIT <= DAILY_LOSS_CAP:
        print("Daily loss cap reached. Skipping buy entries.")
        return

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue

        candles = fetch_recent_candles(ticker, limit=5)
        if not candles or len(candles) < 2:
            continue

        pattern = None
        if is_hammer(candles[-1]):
            pattern = "Hammer"
        elif is_bullish_engulfing(candles[-2], candles[-1]):
            pattern = "Bullish Engulfing"
        elif is_marubozu(candles[-1]):
            pattern = "Marubozu"

        if not pattern:
            continue

        entry_price, _ = fetch_price(ticker)
        vwap = fetch_vwap(ticker)

        if not entry_price or not vwap:
            continue

        distance_from_vwap = abs(entry_price - vwap) / vwap
        if distance_from_vwap > VWAP_TOLERANCE:
            print(f"{ticker}: Rejected {pattern} — too far from VWAP ({distance_from_vwap:.3%})")
            continue

        avg_volume = sum(c['v'] for c in candles[:-1]) / (len(candles) - 1)
        last_volume = candles[-1]['v']
        if last_volume < avg_volume:
            print(f"{ticker}: Rejected {pattern} — weak volume ({last_volume} < avg {avg_volume:.1f})")
            continue

        POSITIONS[ticker] = {
            'entry_price': entry_price,
            'last_price': entry_price,
            'trail_active': False,
            'peak_price': entry_price,
            'cumulative_loss': 0,
            'break_even': False
        }
        print(f"{ticker}: BOUGHT at {entry_price:.2f} based on {pattern} near VWAP with strong volume")
        time.sleep(DELAY)

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
