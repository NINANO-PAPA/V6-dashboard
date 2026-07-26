import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# 모바일 UI 최적화
st.set_page_config(
    page_title="V6 Hybrid System",
    page_icon="📈",
    layout="centered"
)

# 비밀번호 보안 로그인
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 V6 System Access")
        pwd = st.text_input("비밀번호를 입력하세요", type="password")
        if st.button("로그인"):
            if pwd == st.secrets["MY_PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        return False
    return True

if check_password():
    @st.cache_data(ttl=3600)
    def load_tqqq_data():
        df = yf.download("TQQQ", period="1y", interval="1d")
        if isinstance(df.columns, pd.MultiIndex):
            close = df['Close']['TQQQ']
        else:
            close = df['Close']
            
        df['SMA200'] = close.rolling(window=200).mean()
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df, float(close.iloc[-1]), float(df['SMA200'].iloc[-1]), float(df['RSI'].iloc[-1])

    try:
        df, current_price, sma_200, current_rsi = load_tqqq_data()
        avg_cost = 48.10
        total_shares = 687
        returns = ((current_price - avg_cost) / avg_cost) * 100
        sma_margin = ((current_price - sma_200) / sma_200) * 100

        st.title("🛡️ V6 Hybrid Dashboard")
        st.caption("TQQQ Quantitative Portfolio Manager")
        st.divider()

        # 메인 신호등
        if current_price < sma_200:
            st.error("🚨 [🔴 Risk-Off 대피 신호] 200일선 하향 이탈! 전량 매도 후 SGOV 피신")
        elif current_rsi <= 30:
            st.warning("⚡ [🟢 1단계 매수 신호] RSI 30 이하 과매도 진입! 탈출 시 SGOV 20% 집행")
        elif returns >= 100:
            st.info("🎯 [🔵 2단계 익절 타점] +100% 도달! 172주 매도 ➔ SPYM 스위칭")
        else:
            st.success("🟢 [HOLD] 정배열 강세장 유지 중 (신호 대기)")

        st.subheader("📊 실시간 퀀트 지표")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("TQQQ 종가", f"${current_price:.2f}", f"{returns:+.2f}%")
            st.metric("일봉 RSI (14)", f"{current_rsi:.2f}", "RMA Wilder's")
        with col2:
            st.metric("200일선 (SMA)", f"${sma_200:.2f}", f"{sma_margin:+.2f}% (버퍼)")
            st.metric("보유 수량", f"{total_shares} 주", f"평단 ${avg_cost:.2f}")

        st.divider()

        # 익절 트래커
        target_price_100 = avg_cost * 2.0
        progress = min(max(returns / 100.0, 0.0), 1.0)
        st.subheader("🎯 +100% 익절 타점 트래커 ($96.20)")
        st.progress(progress)
        st.write(f"현재 달성도: **{returns:.1f}% / 100.0%** (잔여 격차: **${target_price_100 - current_price:.2f}**)")

        st.divider()
        st.caption("※ TradingView 일봉 D 기준 및 RMA Wilder's 로직 적용")

    except Exception as e:
        st.error(f"데이터 로딩 실패: {e}")
