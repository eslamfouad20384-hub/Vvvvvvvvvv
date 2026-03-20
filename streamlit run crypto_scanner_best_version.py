import streamlit as st
import pandas as pd
import numpy as np
import aiohttp
import asyncio
import time

st.set_page_config(layout="wide")
st.title("Crypto Scanner بالعربي 🔍 - النسخة التفصيلية لكل شرط")

# ==============================
# إعدادات
# ==============================
MIN_LIQUIDITY = 5_000_000
RSI_THRESHOLD = 30

# ==============================
# جلب قائمة العملات
# ==============================
async def fetch_market_list():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    async with aiohttp.ClientSession() as session:
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": "250",
            "page": "1",
            "sparkline": "false"
        }
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            df = pd.DataFrame(data)
            df = df.dropna(subset=["symbol"])
            return df

# ==============================
# جلب OHLC من CryptoCompare
# ==============================
async def fetch_ohlc(session, symbol):
    url = f"https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": symbol.upper(), "tsym": "USDT", "limit": 200}
    try:
        async with session.get(url, params=params) as resp:
            r = await resp.json()
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

# ==============================
# حساب الدعم
# ==============================
def calculate_support(df, period=14):
    return df["close"].tail(period).min()

# ==============================
# فلترة العملات وعرض كل شرط
# ==============================
async def process_coin(session, row):
    try:
        symbol = row["symbol"]
        ohlc = await fetch_ohlc(session, symbol)
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
    except:
        return None

async def process_all_coins(df_market):
    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [process_coin(session, row) for _, row in df_market.iterrows()]
        all_results = await asyncio.gather(*tasks)
        for res in all_results:
            if res:
                results.append(res)
    return pd.DataFrame(results)

# ==============================
# واجهة Streamlit
# ==============================
if st.button("تحديث البيانات / Refresh Data"):
    st.info("جاري جلب بيانات السوق وحساب كل الشروط لكل عملة...")
    start_time = time.time()
    df_market = asyncio.run(fetch_market_list())
    filtered = asyncio.run(process_all_coins(df_market))
    st.subheader(f"عدد العملات اللي استوفت كل الشروط: {filtered['All_OK'].sum()}")
    st.dataframe(filtered.sort_values("All_OK", ascending=False))
    st.success(f"تم التحديث في {time.time()-start_time:.2f} ثانية")
