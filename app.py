import streamlit as st
import pandas as pd
import yfinance as yf
from streamlit_gsheets import GSheetsConnection

# ---------------------------------------------------------
# 1. 페이지 및 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="V6 Hybrid Dashboard", page_icon="🛡️", layout="wide")

# 비밀번호 인증 로직
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 V6 Hybrid Dashboard Access")
        pwd_input = st.text_input("비밀번호를 입력하세요", type="password")
        if st.button("로그인"):
            if pwd_input == st.secrets.get("MY_PASSWORD", "1234"):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
        return False
    return True

if not check_password():
    st.stop()

# ---------------------------------------------------------
# 2. 데이터 수집 함수 (yfinance: TQQQ + QQQ 각각 안전 호출)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_market_data():
    # TQQQ 및 QQQ 단일 티커 호출 (안정성 확보)
    tqqq_obj = yf.Ticker("TQQQ")
    qqq_obj = yf.Ticker("QQQ")
    
    # 히스토리 데이터 다운로드
    df_tqqq = tqqq_obj.history(period="1y")
    df_qqq = qqq_obj.history(period="6m")

    # 데이터 수집 실패 시 예외 처리 (방어 코드)
    if df_tqqq.empty or df_qqq.empty:
        st.error("yfinance 데이터 수집에 실패했습니다. 잠시 후 다시 시도해주세요.")
        st.stop()

    # [TQQQ 지표 계산]
    tqqq_close = float(df_tqqq['Close'].iloc[-1])
    tqqq_200sma = float(df_tqqq['Close'].rolling(window=200).mean().iloc[-1])
    
    # TQQQ RSI(14) 계산 (RMA Wilder's 방식)
    delta = df_tqqq['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    tqqq_rsi = float((100 - (100 / (1 + rs))).iloc[-1])

    # [QQQ 지표 계산]
    qqq_close = float(df_qqq['Close'].iloc[-1])
    qqq_5sma = float(df_qqq['Close'].rolling(window=5).mean().iloc[-1])
    qqq_20sma = float(df_qqq['Close'].rolling(window=20).mean().iloc[-1])
    
    # QQQ 이전 날짜 이평선 (크로스 발생 여부 확인용)
    qqq_5sma_prev = float(df_qqq['Close'].rolling(window=5).mean().iloc[-2])
    qqq_20sma_prev = float(df_qqq['Close'].rolling(window=20).mean().iloc[-2])

    # QQQ 기준 골든크로스 / 데드크로스 판정
    is_golden_cross = bool((qqq_5sma_prev <= qqq_20sma_prev) and (qqq_5sma > qqq_20sma))
    is_dead_cross = bool((qqq_5sma_prev >= qqq_20sma_prev) and (qqq_5sma < qqq_20sma))

    return {
        "tqqq_close": tqqq_close,
        "tqqq_200sma": tqqq_200sma,
        "tqqq_rsi": tqqq_rsi,
        "qqq_close": qqq_close,
        "qqq_5sma": qqq_5sma,
        "qqq_20sma": qqq_20sma,
        "is_golden_cross": is_golden_cross,
        "is_dead_cross": is_dead_cross
    }

market_data = fetch_market_data()

# ---------------------------------------------------------
# 3. 구글 시트 데이터 연동
# ---------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def get_default_df():
    return pd.DataFrame([{
        "qty": 687, "avg_price": 48.10,
        "buy_1": False, "buy_2": False, "buy_3": False,
        "sell_50": False, "sell_100": False, "sell_150": False, "sell_200": False,
        "sell_dead": False, "sell_rsi80": False, "sell_ath": False
    }])

def load_sheet_data():
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if df.empty or "qty" not in df.columns:
            return get_default_df()
        return df
    except Exception:
        return get_default_df()

df_current = load_sheet_data()

# ---------------------------------------------------------
# 4. 사이드바 (계좌 설정)
# ---------------------------------------------------------
st.sidebar.title("⚙️ 내 계좌 설정")
input_qty = st.sidebar.number_input("보유 수량 (주)", value=int(df_current.loc[0, "qty"]), step=1)
input_avg = st.sidebar.number_input("매수 평단가 ($)", value=float(df_current.loc[0, "avg_price"]), step=0.1)

if st.sidebar.button("🔒 로그아웃"):
    st.session_state["password_correct"] = False
    st.rerun()

# ---------------------------------------------------------
# 5. 메인 대시보드 UI
# ---------------------------------------------------------
st.title("🛡️ V6 Hybrid Dashboard")
st.caption("TQQQ Quantitative Portfolio Manager (Google Sheets Sync)")

# 200일선 대피 경고 바너 (TQQQ 기준)
is_danger = market_data["tqqq_close"] < market_data["tqqq_200sma"]
if is_danger:
    st.error("🚨 [DANGER] TQQQ가 200일선 아래로 하락했습니다! SGOV 대피 시그널 가동!")
else:
    st.success("🟢 [HOLD] TQQQ가 200일선 위 정배열 강세장을 유지 중입니다.")

# ---------------------------------------------------------
# 📊 실시간 퀀트 지표 (TQQQ & QQQ 이원화)
# ---------------------------------------------------------
st.subheader("📊 실시간 퀀트 지표")

col1, col2, col3, col4 = st.columns(4)

# 1) TQQQ 정보
with col1:
    st.metric("TQQQ 현재가", f"${market_data['tqqq_close']:.2f}")
    st.caption(f"200일선: ${market_data['tqqq_200sma']:.2f}")

# 2) QQQ 정보 (추가됨)
with col2:
    st.metric("QQQ 현재가", f"${market_data['qqq_close']:.2f}")
    st.caption(f"5일선: ${market_data['qqq_5sma']:.2f} | 20일선: ${market_data['qqq_20sma']:.2f}")

# 3) TQQQ RSI & 200일선 버퍼
with col3:
    buffer_pct = ((market_data['tqqq_close'] - market_data['tqqq_200sma']) / market_data['tqqq_200sma']) * 100
    st.metric("TQQQ 일봉 RSI (14)", f"{market_data['tqqq_rsi']:.2f}")
    st.caption(f"200일선 버퍼: {buffer_pct:+.2f}%")

# 4) 계좌 평가
with col4:
    total_val = input_qty * market_data['tqqq_close']
    profit_pct = ((market_data['tqqq_close'] - input_avg) / input_avg) * 100
    st.metric("보유 자산 평가액", f"${total_val:,.2f}")
    st.caption(f"수익률: {profit_pct:+.2f}% (평단 ${input_avg:.2f})")

st.divider()

# ---------------------------------------------------------
# 🚦 V6 전략 실시간 시그널 현황
# ---------------------------------------------------------
st.subheader("🚦 V6 전략 실시간 시그널 현황")
st.caption("시장 데이터를 실시간 분석하여 조건 포착 시 초록불(🟢), 미달성 시 빨간불(🔴)로 표시됩니다.")

sig_col1, sig_col2, sig_col3 = st.columns(3)

# 1) 매수 시그널
with sig_col1:
    st.markdown("#### 🛒 매수 조건 (분할 진입)")
    
    # 1단계: TQQQ RSI
    b1_status = "🟢 활성 (RSI 35 이하 탈출)" if market_data["tqqq_rsi"] <= 35 else "🔴 비활성"
    # 2단계: QQQ 기준 골든크로스
    b2_status = "🟢 활성 (QQQ 5/20일 골든크로스)" if market_data["is_golden_cross"] else "🔴 비활성"
    # 3단계: TQQQ 200일선
    b3_status = "🟢 활성 (TQQQ 200일선 위)" if not is_danger else "🔴 비활성 (200일선 밑)"

    st.write(f"• **1단계 (RSI 반등)**: {b1_status}")
    st.write(f"• **2단계 (QQQ 골든크로스)**: {b2_status}")
    st.write(f"• **3단계 (TQQQ 200일선 돌파)**: {b3_status}")

# 2) 리스크 및 대피 시그널
with sig_col2:
    st.markdown("#### 🚨 위험 관리 (대피/데드크로스)")
    
    risk_status = "🚨 **경고! TQQQ 200일선 이탈 (SGOV 전량 대피)**" if is_danger else "🟢 **안전 (TQQQ 200일선 위)**"
    dead_status = "🚨 **QQQ 5일/20일 데드크로스 발생!**" if market_data["is_dead_cross"] else "🟢 **정상 (QQQ 이평선 정배열/유지)**"
    
    st.write(f"• **200일선 대피**: {risk_status}")
    st.write(f"• **QQQ 데드크로스**: {dead_status}")

# 3) 익절 및 리밸런싱 시그널
with sig_col3:
    st.markdown("#### 🎯 익절 조건 (SPYM 전환)")
    
    s50 = "🟢 달성 (+50%)" if profit_pct >= 50 else "🔴 미달성"
    s100 = "🟢 달성 (+100%)" if profit_pct >= 100 else "🔴 미달성"
    s150 = "🟢 달성 (+150%)" if profit_pct >= 150 else "🔴 미달성"
    s200 = "🟢 달성 (+200%)" if profit_pct >= 200 else "🔴 미달성"
    srsi80 = "🟢 과열 (TQQQ RSI 80 이상)" if market_data["tqqq_rsi"] >= 80 else "🔴 미달성"

    st.write(f"• **수익률 +50%**: {s50}")
    st.write(f"• **수익률 +100%**: {s100}")
    st.write(f"• **수익률 +150%**: {s150}")
    st.write(f"• **수익률 +200%**: {s200}")
    st.write(f"• **TQQQ RSI 80 이상**: {srsi80}")

st.divider()

# ---------------------------------------------------------
# 📝 매매 체크리스트 & 구글 시트 동기화
# ---------------------------------------------------------
st.subheader("📝 V6 매매 실행 체크리스트 (구글 시트 동기화)")

with st.form("checklist_form"):
    st.write("실제로 매매를 완료하셨다면 아래 항목을 체크하고 [구글 시트에 저장]을 눌러주세요.")
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("**[매수 실행]**")
        chk_b1 = st.checkbox("1단계 매수 완료 (20%)", value=bool(df_current.loc[0, "buy_1"]))
        chk_b2 = st.checkbox("2단계 매수 완료 (30%)", value=bool(df_current.loc[0, "buy_2"]))
        chk_b3 = st.checkbox("3단계 매수 완료 (50%)", value=bool(df_current.loc[0, "buy_3"]))

    with c2:
        st.markdown("**[익절 실행 -> SPYM 매수]**")
        chk_s50 = st.checkbox("+50% 달성 익절 (10%)", value=bool(df_current.loc[0, "sell_50"]))
        chk_s100 = st.checkbox("+100% 달성 익절 (15%)", value=bool(df_current.loc[0, "sell_100"]))
        chk_s150 = st.checkbox("+150% 달성 익절 (15%)", value=bool(df_current.loc[0, "sell_150"]))
        chk_s200 = st.checkbox("+200% 달성 익절 (20%)", value=bool(df_current.loc[0, "sell_200"]))

    with c3:
        st.markdown("**[조건부 익절 실행]**")
        chk_sdead = st.checkbox("QQQ 데드크로스 익절 (15%)", value=bool(df_current.loc[0, "sell_dead"]))
        chk_srsi80 = st.checkbox("RSI 80 이상 익절 (20%)", value=bool(df_current.loc[0, "sell_rsi80"]))
        chk_sath = st.checkbox("전고점 돌파 익절 (10%)", value=bool(df_current.loc[0, "sell_ath"]))

    submit_btn = st.form_submit_button("💾 구글 시트에 매매 현황 저장하기")

if submit_btn:
    updated_df = pd.DataFrame([{
        "qty": input_qty,
        "avg_price": input_avg,
        "buy_1": chk_b1, "buy_2": chk_b2, "buy_3": chk_b3,
        "sell_50": chk_s50, "sell_100": chk_s100, "sell_150": chk_s150, "sell_200": chk_s200,
        "sell_dead": chk_sdead, "sell_rsi80": chk_srsi80, "sell_ath": chk_sath
    }])
    
    try:
        conn.update(worksheet="Sheet1", data=updated_df)
        st.toast("💾 구글 시트에 성공적으로 동기화되었습니다!", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")
