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

if not check_password():
    st.stop()

# ---------------------------------------------------------
# 1. 구글 시트 연동 및 데이터 관리
# ---------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_data():
    try:
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
        return None, None, None, None, None

    close = df['Close'].dropna()
    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    change_pct = ((latest_close - prev_close) / prev_close) * 100

    # 200일 이동평균선 (SMA)
    sma200 = close.rolling(window=200).mean()
    latest_sma200 = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None

    # 5일 / 20일 이동평균선 (골든크로스 판단용)
    sma5 = close.rolling(window=5).mean().iloc[-1]
    sma20 = close.rolling(window=20).mean().iloc[-1]
    is_golden_cross = sma5 > sma20

    # RSI 14 (Wilder's RMA 방식)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None

    return latest_close, change_pct, latest_sma200, latest_rsi, is_golden_cross

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

if st.sidebar.button("🔒 로그아웃"):
    st.session_state["authenticated"] = False
    st.rerun()

# 퀀트 지표 수집
latest_close, change_pct, sma200, rsi14, is_golden_cross = calculate_indicators("TQQQ")

if latest_close is not None and sma200 is not None and rsi14 is not None:
    sma_buffer = ((latest_close - sma200) / sma200) * 100
    is_danger = latest_close < sma200
    total_profit_pct = ((latest_close - input_avg) / input_avg) * 100 if input_avg > 0 else 0

    # 상단 메인 경고 상태
    if not is_danger:
        st.success("🟢 [HOLD] 200일선 위 정배열 강세장 유지 중")
    else:
        st.error("🚨 [ALERT] 200일선 하향 이탈! 전량 매도 및 SGOV 대피 조건 발동")

    # 수치 지표 카드
    st.subheader("📊 실시간 퀀트 지표")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("TQQQ 종가", f"${latest_close:.2f}", f"{change_pct:+.2f}%")
        st.metric("일봉 RSI (14)", f"{rsi14:.2f}", "RMA Wilder's")

    with col2:
        st.metric("200일선 (SMA)", f"${sma200:.2f}", f"{sma_buffer:+.2f}% (버퍼)")
        total_eval = latest_close * input_qty
        st.metric("보유 자산 평가액", f"${total_eval:,.2f}", f"평단 ${input_avg:.2f} ({total_profit_pct:+.2f}%)")

    st.divider()

    # ---------------------------------------------------------
    # 4. 실시간 시그널 모니터링 (🟢 / 🔴)
    # ---------------------------------------------------------
    st.subheader("🚦 V6 전략 실시간 시그널 현황")
    st.caption("현재 실시간 수치를 분석하여 조건 포착 시 초록불(🟢), 미달성 시 빨간불(🔴)로 표시됩니다.")

    sig_col1, sig_col2, sig_col3 = st.columns(3)

    # 매수 시그널 상태
    with sig_col1:
        st.markdown("#### 🛒 매수 조건 포착")
        buy1_sig = "🟢 활성 (RSI 35 이하 진입/탈출)" if rsi14 <= 35 else "🔴 비활성 (정상)"
        buy2_sig = "🟢 활성 (5일-20일 골든크로스)" if is_golden_cross else "🔴 비활성"
        buy3_sig = "🟢 활성 (200일선 위 강세장)" if not is_danger else "🔴 비활성 (200일선 밑)"

        st.write(f"• **1단계 (RSI 반등)**: {buy1_sig}")
        st.write(f"• **2단계 (골든크로스)**: {buy2_sig}")
        st.write(f"• **3단계 (200일선 돌파)**: {buy3_sig}")

    # 리스크 및 대피 시그널 상태
    with sig_col2:
        st.markdown("#### 🚨 위험 관리 시그널")
        risk_sig = "🚨 **경고! 200일선 이탈 (SGOV 전량 대피)**" if is_danger else "🟢 **안전 (200일선 위 유지)**"
        st.write(f"• **200일선 이탈 여부**: {risk_sig}")

    # 익절 및 리밸런싱 시그널 상태
    with sig_col3:
        st.markdown("#### 🎯 익절/리밸런싱 조건")
        s50 = "🟢 달성 (+50% 매도)" if total_profit_pct >= 50 else "🔴 미달성"
        s100 = "🟢 달성 (+100% 매도)" if total_profit_pct >= 100 else "🔴 미달성"
        s150 = "🟢 달성 (+150% 매도)" if total_profit_pct >= 150 else "🔴 미달성"
        s200 = "🟢 달성 (+200% 매도)" if total_profit_pct >= 200 else "🔴 미달성"
        srsi80 = "🟢 달성 (RSI 80 이상 과열)" if rsi14 >= 80 else "🔴 미달성"

        st.write(f"• **수익률 +50%**: {s50}")
        st.write(f"• **수익률 +100%**: {s100}")
        st.write(f"• **수익률 +150%**: {s150}")
        st.write(f"• **수익률 +200%**: {s200}")
        st.write(f"• **RSI 80 이상**: {srsi80}")

    st.divider()

    # ---------------------------------------------------------
    # 5. 매매 실행 체크리스트 (구글 시트 저장)
    # ---------------------------------------------------------
    st.subheader("📋 V6 전략 매매 실행 체크리스트")
    st.caption("실제 주문 및 매매를 완료한 항목을 체크하고 구글 시트에 기록합니다.")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 🛒 3단계 분할 매수 실행 기록")
        b1 = st.checkbox("1단계: RSI 과매도 탈출 (20% 5일 분할 완료)", value=bool(df_current.loc[0, "buy_1"]))
        b2 = st.checkbox("2단계: 골든크로스 발생 (30% 3일 분할 완료)", value=bool(df_current.loc[0, "buy_2"]))
        b3 = st.checkbox("3단계: 200일선 상향 돌파 (50% 5~10일 분할 완료)", value=bool(df_current.loc[0, "buy_3"]))

    with c2:
        st.markdown("### 🎯 7가지 익절 및 리밸런싱 실행 기록")
        s1 = st.checkbox("1. 수익률 +50% 달성 (10% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_50"]))
        s2 = st.checkbox("2. 수익률 +100% 달성 (15% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_100"]))
        s3 = st.checkbox("3. 수익률 +150% 달성 (15% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_150"]))
        s4 = st.checkbox("4. 수익률 +200% 달성 (20% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_200"]))
        s5 = st.checkbox("5. 상승 중 데드크로스 발생 (15% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_dead"]))
        s6 = st.checkbox("6. RSI 80 이상 진입 (20% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_rsi80"]))
        s7 = st.checkbox("7. 전고점 돌파 (10% 매도 후 SPYM)", value=bool(df_current.loc[0, "sell_ath"]))

    st.write("")
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
