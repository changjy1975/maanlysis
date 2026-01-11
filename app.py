import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from io import StringIO
import plotly.graph_objects as go
import urllib3
import time

# 關閉 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台股快篩器 (狀態記憶版)", layout="wide")

# --- 1. 初始化 Session State ---
# 如果 'scan_results' 不在狀態中，先給它一個空值
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = None

@st.cache_data(ttl=86400)
def get_twse_tickers():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, verify=False)
        df = pd.read_html(StringIO(res.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['Code'] = df['有價證券代號及名稱'].str.split('　').str[0]
        tickers = df[df['Code'].str.len() == 4]['Code'].tolist()
        return [t + ".TW" for t in tickers]
    except Exception as e:
        st.error(f"獲取清單失敗: {e}")
        return []

def process_data(all_data, tickers, conv_limit):
    results = []
    for ticker in tickers:
        try:
            df = all_data[ticker].dropna()
            if len(df) < 60: continue
            
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA60'] = df['Close'].rolling(60).mean()
            df['VolMA5'] = df['Volume'].rolling(5).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            cond_vol = curr['VolMA5'] >= 2000000
            cond_bullish = curr['MA5'] > curr['MA10'] > curr['MA20'] > curr['MA60']
            
            ma_list = [prev['MA5'], prev['MA10'], prev['MA20']]
            gap = (max(ma_list) - min(ma_list)) / min(ma_list)
            cond_converged = gap <= (conv_limit / 100)
            
            if cond_vol and cond_bullish and cond_converged:
                results.append({
                    "代號": ticker,
                    "現價": round(float(curr['Close']), 2),
                    "5日均量(張)": int(curr['VolMA5'] / 1000),
                    "糾結度": f"{gap:.2%}"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🚀 台股快篩器 (狀態記憶版)")

with st.sidebar:
    st.header("篩選參數")
    conv_limit = st.slider("均線糾結寬度 (%)", 1.0, 8.0, 3.0)
    
    # 點擊按鈕才會觸發掃描
    if st.button("開始極速掃描"):
        tickers = get_twse_tickers()
        if tickers:
            start_time = time.time()
            with st.spinner(f"正在批次下載並分析 {len(tickers)} 檔股票..."):
                all_data = yf.download(tickers, period="80d", group_by='ticker', threads=True, progress=False)
                # 將結果存入 session_state
                st.session_state['scan_results'] = process_data(all_data, tickers, conv_limit)
            st.success(f"掃描完成！耗時: {int(time.time() - start_time)} 秒")

# --- 顯示結果區域 ---
# 只要 session_state 裡面有資料，就把它顯示出來，不管有沒有按按鈕
if st.session_state['scan_results']:
    res_df = pd.DataFrame(st.session_state['scan_results'])
    
    st.subheader(f"篩選結果 (共 {len(res_df)} 檔)")
    st.dataframe(res_df, use_container_width=True)
    
    st.divider()
    
    # 圖表預覽區
    st.subheader("📊 個股技術圖表預覽")
    # 當切換 selectbox 時，只會重新執行下面這段繪圖邏輯，不會觸發上面的掃描按鈕
    selected = st.selectbox("選擇股票查看線圖", res_df['代號'].tolist())
    
    if selected:
        with st.spinner(f"正在讀取 {selected} 線圖..."):
            plot_df = yf.download(selected, period="150d", progress=False)
            plot_df['MA5'] = plot_df['Close'].rolling(5).mean()
            plot_df['MA10'] = plot_df['Close'].rolling(10).mean()
            plot_df['MA20'] = plot_df['Close'].rolling(20).mean()
            plot_df['MA60'] = plot_df['Close'].rolling(60).mean()
            
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], 
                low=plot_df['Low'], close=plot_df['Close'], name="K線"
            ))
            
            colors = ['#1f77b4', '#ff7f0e', '#9467bd', '#2ca02c']
            for ma, color in zip(['MA5', 'MA10', 'MA20', 'MA60'], colors):
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[ma], line=dict(width=1.5, color=color), name=ma))
            
            fig.update_layout(
                xaxis_rangeslider_visible=False, 
                height=600, 
                template="plotly_dark", 
                title=f"{selected} 走勢圖",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("請點擊左側面板的「開始極速掃描」按鈕來獲取今日推薦標的。")
