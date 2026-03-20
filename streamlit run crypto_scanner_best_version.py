import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

st.set_page_config(layout="wide")
st.title("👑 Crypto Scanner PRO MAX")

# ==============================
# إعدادات
# ==============================
MIN_LIQUIDITY = 10_000_000
RSI_THRESHOLD = 30
MAX_WORKERS = 8

# ==============================
# Request آمن
# ==============================
def safe_request(url, params=None):
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
    except:
        return None

# ==============================
# جلب السوق
# ==============================
def fetch_market_list():
    all_data = []
    page = 1

    while True:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 250,
            "page": page,
        }

        data = safe_request(url, params)

        if not isinstance(data, list) or len(data) == 0:
            break

        clean = [x for x in data if isinstance(x, dict) and "symbol" in x]
        all_data.extend(clean)
        page += 1

    df = pd.DataFrame(all_data)

    if df.empty:
        st.error("❌ فشل جلب السوق")
        st.stop()

    df = df[df["total_volume"] > MIN_LIQUIDITY]

    st.write(f"📊 عدد العملات بعد الفلترة: {len(df)}")
    return df

# ==============================
# Cache OHLC
# ==============================
@lru_cache(maxsize=500)
def fetch_ohlc(symbol, timeframe="hour"):
    if timeframe == "hour":
        url = "https://min-api.cryptocompare.com/data/v2/histohour"
    else:
        url = "https://min-api.cryptocompare.com/data/v2/histominute"

    params = {"fsym": symbol.upper(), "tsym": "USDT", "limit": 100}

    data = safe_request(url, params)
    if not data or "Data" not in data:
        return None

    df = pd.DataFrame(data["Data"]["Data"])
    if df.empty or "close" not in df.columns:
        return None

    return df

# ==============================
# RSI احترافي
# ==============================
def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period).mean()
    avg_loss = loss.ewm(alpha=1/period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ==============================
# تحليل العملة
# ==============================
def process_coin(row):
    try:
        symbol = row["symbol"]

        ohlc_1h = fetch_ohlc(symbol, "hour")
        ohlc_15m = fetch_ohlc(symbol, "minute")

        if ohlc_1h is None or ohlc_15m is None:
            return None

        # RSI
        ohlc_1h["rsi"] = calculate_rsi(ohlc_1h)
        ohlc_15m["rsi"] = calculate_rsi(ohlc_15m)

        rsi_1h = ohlc_1h["rsi"].iloc[-1]
        rsi_prev = ohlc_1h["rsi"].iloc[-2]
        rsi_15m = ohlc_15m["rsi"].iloc[-1]

        rsi_ok = (rsi_1h < 30) and (rsi_1h > rsi_prev)

        # Trend
        ema50 = ohlc_1h["close"].ewm(span=50).mean().iloc[-1]
        ema200 = ohlc_1h["close"].ewm(span=200).mean().iloc[-1]
        trend_ok = ema50 > ema200

        # دعم
        support = ohlc_1h["close"].tail(14).min()
        price = row.get("current_price", 0)
        support_ok = price <= support * 1.02

        # Volume
        if "volumeto" not in ohlc_1h.columns:
            return None

        volume_now = ohlc_1h["volumeto"].iloc[-1]
        volume_avg = ohlc_1h["volumeto"].rolling(20).mean().iloc[-1]
        volume_ok = volume_now > volume_avg * 1.2

        buy_pressure = volume_now > volume_avg

        # سيولة
        liquidity = row.get("total_volume", 0)
        liquidity_ok = liquidity > MIN_LIQUIDITY

        # Pump filter
        price_change = row.get("price_change_percentage_24h", 0)
        not_pumped = price_change < 20

        # FDV
        market_cap = row.get("market_cap", 0)
        fdv = row.get("fully_diluted_valuation", 0)

        fdv_ok = True
        if fdv and market_cap:
            fdv_ok = (fdv / market_cap) < 3

        # =====================
        # SCORE
        # =====================
        score = 0

        if rsi_ok: score += 25
        if volume_ok: score += 20
        if support_ok: score += 15
        if liquidity_ok: score += 10
        if buy_pressure: score += 10
        if trend_ok: score += 10
        if not_pumped: score += 5
        if fdv_ok: score += 5

        # =====================
        # SIGNAL
        # =====================
        if score >= 80:
            signal = "🔥 BUY"
        elif score >= 50:
            signal = "⚠ WAIT"
        else:
            signal = "❌ SKIP"

        return {
            "Symbol": symbol.upper(),
            "Price": price,
            "RSI_1H": round(rsi_1h, 2),
            "RSI_15M": round(rsi_15m, 2),
            "Volume_Now": round(volume_now, 2),
            "Volume_Avg": round(volume_avg, 2),
            "Liquidity": liquidity,
            "Support": round(support, 4),
            "Trend": trend_ok,
            "Buy_Pressure": buy_pressure,
            "Score": score,
            "Signal": signal
        }

    except:
        return None

# ==============================
# الواجهة
# ==============================
if st.button("🚀 تشغيل الفحص الاحترافي"):
    st.info("⏳ جاري التحليل...")

    start = time.time()
    df_market = fetch_market_list()

    results = []
    progress = st.progress(0)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_coin, row) for _, row in df_market.iterrows()]

        for i, future in enumerate(futures):
            res = future.result()
            if res:
                results.append(res)
            progress.progress((i + 1) / len(futures))

    df = pd.DataFrame(results)

    if df.empty:
        st.warning("❌ لا توجد فرص")
    else:
        df = df.sort_values("Score", ascending=False)
        st.success(f"✅ تم التحليل في {round(time.time()-start,2)} ثانية")
        st.dataframe(df)
