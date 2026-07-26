iimport streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ---------------------------------------------------------
# 1. 지표 계산 함수 (Wilder's RMA 적용)
# ---------------------------------------------------------
def calculate_indicators(symbol="TQQQ"):
    # 200일 SMA 및 Wilder's RMA RSI 계산을 위해 2년 치 데이터 수집
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="2y")
    
    if df.empty:
        return None, None, None, None

    # 데이터 구조 안전화 (Series 형태로 추출)
    close = df['Close'].dropna()
    
    # TQQQ 최신 종가 및 전일 대비 변동률
    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    change_pct = ((latest_close - prev_close) / prev_close) * 100

    # 1) 200일 이동평균선 (200 SMA)
    sma200 = close.rolling(window=200).mean()
    latest_sma200 = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None

    # 2) RSI 14 (Wilder's Smoothing / RMA 방식)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # RMA calculation (alpha = 1 / N)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None

    return latest_close, change_pct, latest_sma200, latest_rsi

# ---------------------------------------------------------
# 2. 대시보드 UI 연동
# ---------------------------------------------------------
st.title("🛡️ V6 Hybrid Dashboard")
st.caption("TQQQ Quantitative Portfolio Manager")

# 데이터 로딩
latest_close, change_pct, sma200, rsi14 = calculate_indicators("TQQQ")

# 보유 계좌 예시 데이터 (사용자 설정값)
avg_price = 48.10
holding_qty = 687
target_profit_price = avg_price * 2.0  # +100% 익절 타점 ($96.20)

if latest_close is not None and sma200 is not None and rsi14 is not None:
    
    # 200일선 대비 버퍼 (%)
    sma_buffer = ((latest_close - sma200) / sma200) * 100
    
    # [상태 바]
    if latest_close >= sma200:
        st.success("🟢 [HOLD] 정배열 강세장 유지 중 (신호 대기)")
    else:
        st.error("🚨 [ALERT] 200일선 하향 이탈! 전량 매도 및 SGOV 대피 조건")

    st.subheader("📊 실시간 퀀트 지표")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            label="TQQQ 종가", 
            value=f"${latest_close:.2f}", 
            delta=f"{change_pct:+.2f}%"
        )
        st.metric(
            label="일봉 RSI (14)", 
            value=f"{rsi14:.2f}", 
            delta="RMA Wilder's"
        )

    with col2:
        st.metric(
            label="200일선 (SMA)", 
            value=f"${sma200:.2f}", 
            delta=f"{sma_buffer:+.2f}% (버퍼)"
        )
        st.metric(
            label="보유 수량", 
            value=f"{holding_qty:,} 주", 
            delta=f"평단 ${avg_price:.2f}"
        )

    st.divider()

    # +100% 익절 타점 트래커
    st.subheader(f"🎯 +100% 익절 타점 트래커 (${target_profit_price:.2f})")
    
    # 프로그레스 바 계산 (NaN 및 범위 초과 0.0~1.0 안전 보장)
    progress_val = (latest_close - avg_price) / (target_profit_price - avg_price)
    progress_val = max(0.0, min(1.0, progress_val))  # 0~1 사이로 제한

    st.progress(progress_val)
    st.caption(f"목표가 진척도: {progress_val * 100:.1f}% 달성")

else:
    st.error("데이터 수집 실패: Yahoo Finance 서버 통신 상태를 확인하거나 잠시 후 다시 시도하세요.")
