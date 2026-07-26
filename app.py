import streamlit as st
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import pandas as pd
import numpy as np

# 페이지 기본 설정
st.set_page_config(page_title="V6 Hybrid Dashboard", page_icon="🛡️", layout="wide")

# ---------------------------------------------------------
# 0. 비밀번호 보안 잠금 기능
# ---------------------------------------------------------
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 V6 Dashboard 로그인")
        st.caption("권한이 있는 사용자만 접근할 수 있습니다.")
        
        user_input = st.text_input("비밀번호를 입력하세요", type="password")
        if st.button("로그인", type="primary"):
            if user_input == st.secrets.get("MY_PASSWORD", ""):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 올바르지 않습니다.")
        return False
    return True

# 비밀번호 인증을 통과하지 못하면 이하 코드 실행 중단
if not check_password():
    st.stop()

# ---------------------------------------------------------
# 1. 구글 시트 연동 및 데이터 관리
# ---------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data():
    try:
        # ttl=0 설정으로 캐시 없이 실시간 데이터 동기화
        df = conn.read(worksheet="Sheet1", ttl=0)
        if df.empty:
            return get_default_df()
        return df
    except Exception as e:
        st.error(f"구글 시트 로딩 실패: {e}")
        return get_default_df()

def get_default_df():
    data = {
        "qty": [687], "avg_price": [48.10],
        "buy_1": [False], "buy_2": [False], "buy_3": [False],
        "sell_50": [False], "sell_100": [False], "sell_150": [False],
        "sell_200": [False], "sell_dead": [False], "sell_rsi80": [False], "sell_ath": [False]
    }
    return pd.DataFrame(data)

def save_sheet_data(df):
    try:
        conn.update(worksheet="Sheet1", data=df)
        st.toast("💾 구글 시트에 성공적으로 동기화되었습니다!", icon="✅")
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")

# ---------------------------------------------------------
# 2. 퀀트 지표 계산 (TQQQ 일봉, 200일 SMA, RMA RSI 14)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def calculate_indicators(symbol="TQQQ"):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="2y")
    
    if df.empty:
        return None, None, None, None

    close = df['Close'].dropna()
    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    change_pct = ((latest_close - prev_close) / prev_close) * 100

    # 200일 이동평균선 (SMA)
    sma200 = close.rolling(window=200).mean()
    latest_sma200 = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None

    # RSI 14 (Wilder's RMA 방식)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None

    return latest_close, change_pct, latest_sma200, latest_rsi

# ---------------------------------------------------------
# 3. 대시보드 메인 UI
# ---------------------------------------------------------
st.title("🛡️ V6 Hybrid Dashboard")
st.caption("TQQQ Quantitative Portfolio Manager (Google Sheets Sync)")

# 구글 시트 데이터 로드
df_current = load_sheet_data()

# 사이드바 계좌 설정
st.sidebar.header("⚙️ 내 계좌 설정")
input_qty = st.sidebar.number_input("보유 수량 (주)", value=int(df_current.loc[0, "qty"]), step=1)
input_avg = st.sidebar.number_input("매수 평단가 ($)", value=float(df_current.loc[0, "avg_price"]), step=0.1, format="%.2f")

# 로그아웃 버튼
if st.sidebar.button("🔒 로그아웃"):
    st.session_state["authenticated"] = False
    st.rerun()

# 퀀트 지표 수집
latest_close, change_pct, sma200, rsi14 = calculate_indicators("TQQQ")

if latest_close is not None and sma200 is not None and rsi14 is not None:
    sma_buffer = ((latest_close - sma200) / sma200) * 100
    is_danger = latest_close < sma200

    # 경고 상태
    if not is_danger:
        st.success("🟢 [HOLD] 200일선 위 정배열 강세장 유지 중 (시그널 모니터링)")
    else:
        st.error("🚨 [ALERT] 200일선 하향 이탈! 전량 매도 및 SGOV 대피 조건 발동")

    # 지표 카드
    st.subheader("📊 실시간 퀀트 지표")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("TQQQ 종가", f"${latest_close:.2f}", f"{change_pct:+.2f}%")
        st.metric("일봉 RSI (14)", f"{rsi14:.2f}", "RMA Wilder's")

    with col2:
        st.metric("200일선 (SMA)", f"${sma200:.2f}", f"{sma_buffer:+.2f}% (버퍼)")
        total_eval = latest_close * input_qty
        total_profit_pct = ((latest_close - input_avg) / input_avg) * 100 if input_avg > 0 else 0
        st.metric("보유 자산 평가액", f"${total_eval:,.2f}", f"평단 ${input_avg:.2f} ({total_profit_pct:+.2f}%)")

    st.divider()

    # 200일선 이탈 시 리셋 기능
    if is_danger:
        st.warning("⚠️ 200일선 이하 이탈 상태입니다. 전량 매도 후 동기화 데이터를 초기화할 수 있습니다.")
        if st.button("🔄 대피 실행 (모든 체크리스트 및 보유수량 리셋)"):
            reset_df = get_default_df()
            reset_df.loc[0, "qty"] = 0
            reset_df.loc[0, "avg_price"] = 0.0
            save_sheet_data(reset_df)
            st.rerun()

    # ---------------------------------------------------------
    # 4. 매매 실행 체크리스트
    # ---------------------------------------------------------
    st.subheader("📋 V6 전략 매매 실행 체크리스트")
    st.caption("체크박스 및 수량을 수정한 뒤 아래 [최종 동기화] 버튼을 누르면 PC와 스마트폰에 공통 적용됩니다.")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 🛒 3단계 분할 매수 시그널")
        b1 = st.checkbox("1단계: RSI 과매도 탈출 (20% 5일 분할)", value=bool(df_current.loc[0, "buy_1"]))
        b2 = st.checkbox("2단계: 골든크로스 발생 (30% 3일 분할)", value=bool(df_current.loc[0, "buy_2"]))
        b3 = st.checkbox("3단계: 200일선 상향 돌파 (50% 5~10일 분할)", value=bool(df_current.loc[0, "buy_3"]))

    with c2:
        st.markdown("### 🎯 7가지 익절 및 리밸런싱 (SPYM 전환)")
        s1 = st.checkbox("1. 수익률 +50% 달성 (10% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_50"]))
        s2 = st.checkbox("2. 수익률 +100% 달성 (15% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_100"]))
        s3 = st.checkbox("3. 수익률 +150% 달성 (15% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_150"]))
        s4 = st.checkbox("4. 수익률 +200% 달성 (20% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_200"]))
        s5 = st.checkbox("5. 상승 중 데드크로스 발생 (15% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_dead"]))
        s6 = st.checkbox("6. RSI 80 이상 진입 (20% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_rsi80"]))
        s7 = st.checkbox("7. 전고점 돌파 (10% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_ath"]))

    st.space(2)
    # 데이터 저장 버튼
    if st.button("☁️ 구글 시트로 최종 동기화 저장", type="primary", use_container_width=True):
        new_data = {
            "qty": [input_qty],
            "avg_price": [input_avg],
            "buy_1": [b1], "buy_2": [b2], "buy_3": [b3],
            "sell_50": [s1], "sell_100": [s2], "sell_150": [s3], "sell_200": [s4],
            "sell_dead": [s5], "sell_rsi80": [s6], "sell_ath": [s7]
        }
        updated_df = pd.DataFrame(new_data)
        save_sheet_data(updated_df)
        st.rerun()

else:
    st.error("데이터 수집 실패: Yahoo Finance 데이터 로드 상태를 확인하세요.")
