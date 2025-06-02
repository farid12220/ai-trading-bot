# ... all previous imports and config stay the same

def is_3_bar_play(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]

    # 1st: strong green candle
    c1_body = c1['c'] - c1['o']
    if c1_body <= 0 or c1_body < (c1['h'] - c1['l']) * 0.6:
        return False

    # 2nd: pullback or inside candle
    if c2['h'] > c1['h'] or c2['l'] < c1['l']:
        return False
    if abs(c2['c'] - c2['o']) > c1_body * 0.5:
        return False

    # 3rd: breakout
    return c3['c'] > max(c1['h'], c2['h'])

# ... all previous helper functions unchanged ...

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
        if not candles or len(candles) < 3:
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

# ... main loop stays the same ...

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
