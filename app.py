import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from io import StringIO
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="台股均線糾結篩選器", layout="wide")

@st.cache_data(ttl=86400)
def get_twse_tickers():
    """從證交所抓取上市股票清單"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    res = requests.get(url)
    df = pd.read_html(StringIO(res.text))[0]
    df.columns = df.iloc[0]
    df = df.iloc[1:]
    # 過濾出普通股
    df['Code'] = df['有價證券代號及名稱'].str.split('　').str[0]
    # 只要 4 位數代碼的股票
    tickers = df[df['Code'].str.len() == 4]['Code'].tolist()
    return [t + ".TW" for t in tickers]

def calculate_ma_alignment(df, convergence_threshold):
    if len(df) < 60:
        return False, 0
    
    # 計算均線
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['VolMA5'] = df['Volume'].rolling(5).mean()
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 條件 1: 5日均量 > 2000張 (yfinance單位是股)
    cond_vol = curr['VolMA5'] > 2000000
    
    # 條件 2: 多頭排列 (MA5 > MA10 > MA20 > MA60)
    cond_bullish = curr['MA5'] > curr['MA10'] > curr['MA20'] > curr['MA60']
    
    # 條件 3: 均線糾結 (前一日 MA5, 10, 20 的最大差距在 X% 以內)
    # 通常糾結看短中線即可，60日線作為方向參考
    ma_list = [prev['MA5'], prev['MA10'], prev['MA20']]
    gap = (max(ma_list) - min(ma_list)) / min(ma_list)
    cond_converged = gap < (convergence_threshold / 100)
    
    return (cond_vol and cond_bullish and cond_converged), gap

# --- UI 介面 ---
st.title("📈 台股均線糾結 + 多頭排列篩選器")
st.sidebar.header("篩選參數設定")

vol_limit = st.sidebar.number_input("5日均量大於 (張)", value=2000)
conv_limit = st.sidebar.slider("均線糾結寬度 (%)", 1.0, 5.0, 3.0)

if st.button("開始掃描上市股票"):
    tickers = get_twse_tickers()
    st.info(f"正在分析 {len(tickers)} 檔股票，這可能需要 1-2 分鐘...")
    
    progress_bar = st.progress(0)
    results = []
    
    # 分批下載數據以提高效率
    # 為了示範完整性，此處採用循環下載，若要極速建議配合 yf.download(threads=True)
    for i, ticker in enumerate(tickers):
        progress_bar.progress((i + 1) / len(tickers))
        try:
            # 抓取最近 80 天數據
            stock_df = yf.download(ticker, period="80d", progress=False)
            if stock_df.empty: continue
            
            is_match, gap = calculate_ma_alignment(stock_df, conv_limit)
            
            if is_match:
                curr = stock_df.iloc[-1]
                results.append({
                    "代號": ticker,
                    "現價": round(float(curr['Close']), 2),
                    "5日均量": int(curr['Volume'].rolling(5).mean().iloc[-1] / 1000),
                    "糾結度": f"{gap:.2%}"
                })
        except Exception as e:
            continue

    if results:
        res_df = pd.DataFrame(results)
        st.success(f"篩選完成！共找到 {len(res_df)} 檔符合條件的股票。")
        st.dataframe(res_df, use_container_width=True)
        
        # 畫圖區域
        st.subheader("個股技術圖表預覽")
        selected_stock = st.selectbox("選擇要查看的股票", res_df['代號'].tolist())
        
        if selected_stock:
            plot_df = yf.download(selected_stock, period="150d")
            plot_df['MA5'] = plot_df['Close'].rolling(5).mean()
            plot_df['MA10'] = plot_df['Close'].rolling(10).mean()
            plot_df['MA20'] = plot_df['Close'].rolling(20).mean()
            plot_df['MA60'] = plot_df['Close'].rolling(60).mean()
            
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="K線"))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], line=dict(color='blue', width=1), name="MA5"))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], line=dict(color='orange', width=1), name="MA10"))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], line=dict(color='purple', width=1), name="MA20"))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], line=dict(color='green', width=1), name="MA60"))
            
            fig.update_layout(title=f"{selected_stock} 技術分析圖", xaxis_rangeslider_visible=False, height=600)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("今日無符合條件的股票。")
