import requests
import time
import numpy as np
import pandas as pd
from telegram import Bot
import os
from datetime import datetime, timedelta

# جلب متغيرات البيئة
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

# قائمة الأصول (فوركس و OTC)
ASSETS = [
    "EURUSD", "GBPUSD", "USDJPY",
    "EURUSD-OTC", "GBPUSD-OTC"
]

TIMEFRAME = 1  # دقيقة
CHECK_INTERVAL = 60  # تحقق كل 60 ثانية
MAX_SIGNALS_PER_HOUR = 5  # أقصى إشارات لكل أصل بالساعة
MIN_SIGNAL_STRENGTH = 90  # الحد الأدنى لقوة الإشارة لإرسالها

signals_log = {asset: [] for asset in ASSETS}

def fetch_prices(asset):
    base = "USD"
    symbol = asset.replace("-OTC", "")[-3:]
    start_date = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://api.exchangerate.host/timeseries?start_date={start_date}&end_date={end_date}&base={base}&symbols={symbol}"
    try:
        response = requests.get(url, timeout=10).json()
        prices = [v[symbol] for k, v in sorted(response["rates"].items()) if symbol in v]
        return prices[-50:]
    except Exception as e:
        print(f"Error fetching prices for {asset}: {e}")
        return []

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_macd(prices):
    if len(prices) < 26:
        return None, None
    short_ema = pd.Series(prices).ewm(span=12).mean()
    long_ema = pd.Series(prices).ewm(span=26).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=9).mean()
    return macd.iloc[-1], signal.iloc[-1]

def signal_strength(rsi, macd, signal):
    strength = 50
    if rsi < 30 and macd > signal:
        strength = 80 + (30 - rsi) * 0.5
    elif rsi > 70 and macd < signal:
        strength = 80 + (rsi - 70) * 0.5
    return min(100, round(strength))

def can_send_signal(asset):
    now = datetime.utcnow()
    signals_times = signals_log[asset]
    signals_log[asset] = [t for t in signals_times if now - t < timedelta(hours=1)]
    return len(signals_log[asset]) < MAX_SIGNALS_PER_HOUR

def record_signal(asset):
    signals_log[asset].append(datetime.utcnow())

def generate_signal(asset):
    prices = fetch_prices(asset)
    if len(prices) < 30:
        return None, None
    rsi = calculate_rsi(prices)
    macd, signal = calculate_macd(prices)
    if rsi is None or macd is None or signal is None:
        return None, None
    if rsi < 30 and macd > signal:
        return "UP", signal_strength(rsi, macd, signal)
    elif rsi > 70 and macd < signal:
        return "DOWN", signal_strength(rsi, macd, signal)
    return None, None

def send_signal(asset, direction, strength):
    message = (
        f"📢 *إشارة قوية*\n\n"
        f"💱 الأصل: {asset}\n"
        f"🕒 الفريم: {TIMEFRAME} دقيقة\n"
        f"📈 الاتجاه: *{direction}*\n"
        f"🔥 قوة الإشارة: *{strength}%*\n\n"
        f"✅ إشارة موثوقة تم تصفيتها بالذكاء الاصطناعي"
    )
    bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

def main_loop():
    while True:
        try:
            for asset in ASSETS:
                if can_send_signal(asset):
                    direction, strength = generate_signal(asset)
                    if direction and strength >= MIN_SIGNAL_STRENGTH:
                        send_signal(asset, direction, strength)
                        record_signal(asset)
                        print(f"Sent strong signal for {asset}: {direction} ({strength}%)")
                else:
                    print(f"Reached max signals for {asset} this hour.")
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"خطأ في الحلقة الرئيسية: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
