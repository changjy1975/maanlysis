# Taiwan Stock MA Screener
這是一個基於 Python 與 Streamlit 開發的台股篩選工具。

### 功能
1. 自動抓取全台股上市股票清單。
2. 篩選 **5 日均量 > 2000 張** 的股票。
3. 篩選 **MA5 > MA10 > MA20 > MA60** 的多頭排列股票。
4. 篩選均線糾結（寬度可自訂）後準備噴發的標的。

### 如何執行
1. 安裝環境：`pip install -r requirements.txt`
2. 啟動 App：`streamlit run app.py`
