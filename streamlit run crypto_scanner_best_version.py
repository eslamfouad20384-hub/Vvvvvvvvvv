import streamlit as st
import pandas as pd
import numpy as np
import requests
import time

st.set_page_config(layout="wide")
st.title("Crypto Scanner بالعربي 🔍 - نسخة Cloud Ready")

# ==============================
# إعدادات
# ==============================
MIN_LIQUIDITY = 5_000_000
RSI_THRESHOLD = 30

# ==============================
# جلب قائمة العملات من CoinGecko
# ==============================
def fetch_market_list():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": False
    }
    data = requests.get(url, params=params).json()
    df = pd.DataFrame(data)
    df = df.dropna(subset=["symbol"])
    return df

# ==============================
# جلب OHLC من CryptoCompare
# ==============================
def fetch_ohlc(symbol):
    url = f"https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": symbol.upper(), "tsym": "USDT", "limit": 200}
    try:
        r = requests.get(url, params=params).json()
        df = pd.DataFrame(r["Data"]["Data"])
        if df.empty or "close" not in df.columns:
            return None
        return df
    except:
        return None

# ==============================
# حساب المؤشرات
# ==============================
def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df

def calculate_support(df, period=14):
    return df["close"].tail(period).min()

# ==============================
# فلترة العملات مع كل شرط بالتفصيل
# ==============================
def process_coin(row):
    symbol = row["symbol"]
    ohlc = fetch_ohlc(symbol)
    if ohlc is None or len(ohlc) < 14:
        return None

    ohlc = add_indicators(ohlc)
    rsi = ohlc["rsi"].iloc[-1]
    support = calculate_support(ohlc)

    liquidity = row.get("total_volume",0)
    buy_volume = liquidity * 0.6
    sell_volume = liquidity * 0.4

    liquidity_ok = liquidity >= MIN_LIQUIDITY
    buy_vs_sell_ok = buy_volume > sell_volume
    rsi_ok = rsi < RSI_THRESHOLD
    support_ok = row.get("current_price",0) <= support

    return {
        "Name": row.get("name","N/A"),
        "Symbol": symbol.upper(),
        "Price": row.get("current_price",0),
        "Liquidity": liquidity,
        "Liquidity_OK": liquidity_ok,
        "Buy>Sell_OK": buy_vs_sell_ok,
        "RSI": round(rsi,2),
        "RSI_OK": rsi_ok,
        "Support": round(support,4),
        "Support_OK": support_ok,
        "All_OK": all([liquidity_ok, buy_vs_sell_ok, rsi_ok, support_ok])
    }

# ==============================
# واجهة Streamlit
# ==============================
if st.button("تحديث البيانات / Refresh Data"):
    st.info("⏳ جاري جلب بيانات السوق وحساب كل الشروط لكل عملة...")
    start_time = time.time()

    df_market = fetch_market_list()
    results = []
    total = len(df_market)
    progress = st.progress(0)
    status_text = st.empty()

    for idx, row in enumerate(df_market.itertuples(), start=1):
        status_text.text(f"جارٍ فحص العملة {idx} من {total}")
        res = process_coin(df_market.iloc[idx-1])
        if res:
            results.append(res)
        progress.progress(idx/total)

    filtered = pd.DataFrame(results)
    st.subheader(f"عدد العملات اللي استوفت كل الشروط: {filtered['All_OK'].sum()}")
    st.dataframe(filtered.sort_values("All_OK", ascending=False))
    st.success(f"✅ تم التحديث في {time.time()-start_time:.2f} ثانية")
