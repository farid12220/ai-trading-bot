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
VWAP_TOLERANCE = 0.005

ALL_TICKERS = []
POSITIONS = {}
DAILY_PROFIT = 0

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

def fetch_recent_candles(symbol, limit=6):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?timeframe=1Min&limit={limit}"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if r.status_code == 200:
        return r.json().get("bars", [])
    else:
        return None

# === PATTERNS ===
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
    if total_range == 0:
        return False
    upper_wick = candle['h'] - max(candle['c'], candle['o'])
    lower_wick = min(candle['c'], candle['o']) - candle['l']
    return (
        body / total_range > 0.9 and
        upper_wick / total_range < 0.05 and
        lower_wick / total_range < 0.05
    )

def is_3_bar_play(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    c1_body = c1['c'] - c1['o']
    if c1_body <= 0 or c1_body < (c1['h'] - c1['l']) * 0.6:
        return False
    if c2['h'] > c1['h'] or c2['l'] < c1['l']:
        return False
    if abs(c2['c'] - c2['o']) > c1_body * 0.5:
        return False
    return c3['c'] > max(c1['h'], c2['h'])

def is_inside_bar(candles):
    if len(candles) < 2:
        return False
    prev, curr = candles[-2], candles[-1]
    return curr['h'] < prev['h'] and curr['l'] > prev['l']

def is_breakout_retest(candles):
    if len(candles) < 6:
        return False
    breakout = candles[-6]
    pullback = candles[-5:-1]
    current = candles[-1]
    if breakout['c'] <= breakout['o']:
        return False
    if any(c['l'] < breakout['h'] for c in pullback):
        return False
    return current['c'] > breakout['h']

def is_doji_near_vwap(candle, vwap):
    body = abs(candle['c'] - candle['o'])
    range_ = candle['h'] - candle['l']
    if range_ == 0:
        return False
    if body / range_ > 0.15:
        return False
    return abs(candle['c'] - vwap) / vwap <= VWAP_TOLERANCE

# === LOGGING ===
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
    requests.post(url, json=payload, headers=headers)

# === SCHEDULE ===
def market_is_open():
    eastern = pytz.timezone("US/Eastern")
    now_et = datetime.datetime.now(eastern)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, microsecond=0)
    return market_open <= now_et <= market_close

# === MAIN ===
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
        stop = position['cumulative_loss'] >= 0.0075
        trail = position['trail_active'] and (position['peak_price'] - current_price) / position['peak_price'] >= 0.0075
        break_even = position['break_even'] and current_price < entry_price
        if stop or trail or break_even:
            profit = current_price - entry_price
            insert_trade(ticker, entry_price, current_price, profit)
            del POSITIONS[ticker]
        time.sleep(DELAY)

    if not market_is_open() or DAILY_PROFIT <= DAILY_LOSS_CAP:
        return

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue
        candles = fetch_recent_candles(ticker, limit=6)
        if not candles or len(candles) < 3:
            continue
        entry_price, _ = fetch_price(ticker)
        vwap = fetch_vwap(ticker)
        if not entry_price or not vwap:
            continue

        pattern = None
        if is_hammer(candles[-1]):
            pattern = "Hammer"
        elif is_bullish_engulfing(candles[-2], candles[-1]):
            pattern = "Bullish Engulfing"
        elif is_marubozu(candles[-1]):
            pattern = "Marubozu"
        elif is_3_bar_play(candles):
            pattern = "3-Bar Play"
        elif is_inside_bar(candles):
            pattern = "Inside Bar"
        elif is_breakout_retest(candles):
            pattern = "Breakout + Retest"
        elif is_doji_near_vwap(candles[-1], vwap):
            pattern = "Doji near VWAP"
            pattern = "Doji near VWAP"

        if not pattern:
            continue

        if abs(entry_price - vwap) / vwap > VWAP_TOLERANCE:
            continue
        avg_volume = sum(c['v'] for c in candles[:-1]) / (len(candles) - 1)
        if candles[-1]['v'] < avg_volume:
            continue

        POSITIONS[ticker] = {
            'entry_price': entry_price,
            'last_price': entry_price,
            'trail_active': False,
            'peak_price': entry_price,
            'cumulative_loss': 0,
            'break_even': False
        }
        print(f"{ticker}: BOUGHT at {entry_price:.2f} on {pattern}")
        time.sleep(DELAY)

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")
    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
