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

st.set_page_config(page_title="台股均線糾結篩選器 (批次加速版)", layout="wide")

@st.cache_data(ttl=86400)
def get_twse_tickers():
    """從證交所抓取上市股票清單"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, verify=False)
        df = pd.read_html(StringIO(res.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['Code'] = df['有價證券代號及名稱'].str.split('　').str[0]
        # 只取 4 位數代碼的上市股票
        tickers = df[df['Code'].str.len() == 4]['Code'].tolist()
        return [t + ".TW" for t in tickers]
    except Exception as e:
        st.error(f"獲取清單失敗: {e}")
        return []

def process_data(all_data, tickers, conv_limit):
    """處理批次下載後的 Multi-index DataFrame"""
    results = []
    for ticker in tickers:
        try:
            # 從多重索引中提取個股數據
            df = all_data[ticker].dropna()
            if len(df) < 60: continue
            
            # 計算均線
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA60'] = df['Close'].rolling(60).mean()
            df['VolMA5'] = df['Volume'].rolling(5).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 條件 1: 5日均量 > 2000張 (2,000,000股)
            cond_vol = curr['VolMA5'] >= 2000000
            
            # 條件 2: 多頭排列 (MA5 > MA10 > MA20 > MA60)
            cond_bullish = curr['MA5'] > curr['MA10'] > curr['MA20'] > curr['MA60']
            
            # 條件 3: 均線糾結 (前一日 MA5, 10, 20 的最大差距)
            ma_list = [prev['MA5'], prev['MA10'], prev['MA20']]
            gap = (max(ma_list) - min(ma_list)) / min(ma_list)
            cond_converged = gap <= (conv_limit / 100)
            
            if cond_vol and cond_bullish and cond_converged:
                results.append({
                    "代號": ticker,
                    "名稱": ticker.replace(".TW", ""),
                    "現價": round(float(curr['Close']), 2),
                    "5日均量(張)": int(curr['VolMA5'] / 1000),
                    "糾結度": f"{gap:.2%}"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🚀 台股快篩器 (批次下載版)")
st.sidebar.header("篩選參數")
conv_limit = st.sidebar.slider("均線糾結寬度 (%)", 1.0, 8.0, 3.0)

if st.button("開始極速掃描"):
    tickers = get_twse_tickers()
    
    if tickers:
        start_time = time.time()
        st.info(f"正在批次下載 {len(tickers)} 檔股票數據...")
        
        # 關鍵：使用 threads=True 進行多執行緒下載
        # period="80d" 確保有足夠空間計算 MA60
        all_data = yf.download(tickers, period="80d", interval="1d", group_by='ticker', threads=True, progress=True)
        
        st.info("數據下載完成，正在分析邏輯...")
        final_results = process_data(all_data, tickers, conv_limit)
        
        end_time = time.time()
        st.success(f"掃描完成！耗時: {int(end_time - start_time)} 秒")
        
        if final_results:
            res_df = pd.DataFrame(final_results)
            st.dataframe(res_df, use_container_width=True)
            
            st.divider()
            st.subheader("個股技術圖表")
            selected = st.selectbox("查看詳細圖表", res_df['代號'].tolist())
            
            if selected:
                # 繪圖則維持單獨下載近期更長數據
                plot_df = yf.download(selected, period="150d", progress=False)
                plot_df['MA5'] = plot_df['Close'].rolling(5).mean()
                plot_df['MA10'] = plot_df['Close'].rolling(10).mean()
                plot_df['MA20'] = plot_df['Close'].rolling(20).mean()
                plot_df['MA60'] = plot_df['Close'].rolling(60).mean()
                
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="K線"))
                for ma, color in zip(['MA5', 'MA10', 'MA20', 'MA60'], ['blue', 'orange', 'purple', 'green']):
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[ma], line=dict(width=1.5, color=color), name=ma))
                
                fig.update_layout(xaxis_rangeslider_visible=False, height=600, template="plotly_dark", title=f"{selected} 走勢圖")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("查無符合條件股票，請嘗試放寬「糾結寬度」。")
