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
# 2. 데이터 수집 함수 (yf.download 사용으로 안정성 강화)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_market_data():
    try:
        # yf.download를 사용하여 TQQQ와 QQQ 데이터를 한 번에 안정적으로 수집
        data = yf.download(
            tickers=["TQQQ", "QQQ"],
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False
        )

        # 데이터 존재 여부 검증
        if data.empty or "TQQQ" not in data or "QQQ" not in data:
            st.warning("⚠️ 야후 파이낸스 응답 대기 중입니다. 잠시 후 [Refresh] 버튼을 눌러주세요.")
            st.stop()

        df_tqqq = data["TQQQ"].dropna()
        df_qqq = data["QQQ"].dropna()

        if len(df_tqqq) < 200 or len(df_qqq) < 20:
            st.warning("⚠️ 최소 필요 데이터 건수가 부족합니다.")
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
    except Exception as e:
        st.error(f"데이터 수집 중 오류 발생: {e}")
        st.stop()
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
# 📊 실시간 퀀트 지표 (시인성 극대화 3단계 레이아웃)
# ---------------------------------------------------------
st.subheader("📊 실시간 퀀트 지표")

# [그룹 1] TQQQ 지표 (매수/대피 핵심 기준)
st.markdown("### 🔹 TQQQ 지표 (매수/대피 기준)")
t1, t2, t3 = st.columns(3)
with t1:
    st.metric(label="TQQQ 현재가", value=f"${market_data['tqqq_close']:.2f}")
with t2:
    st.metric(label="TQQQ 일봉 RSI (14)", value=f"{market_data['tqqq_rsi']:.2f}")
with t3:
    buffer_pct = ((market_data['tqqq_close'] - market_data['tqqq_200sma']) / market_data['tqqq_200sma']) * 100
    st.metric(
        label="200일선 (SMA)", 
        value=f"${market_data['tqqq_200sma']:.2f}", 
        delta=f"{buffer_pct:+.2f}% 버퍼"
    )

st.divider()

# [그룹 2] QQQ 지표 (골든/데드크로스 판단 기준)
st.markdown("### 🔸 QQQ 지표 (이평선 추세 기준)")
q1, q2, q3 = st.columns(3)
with q1:
    st.metric(label="QQQ 현재가", value=f"${market_data['qqq_close']:.2f}")
with q2:
    st.metric(label="QQQ 5일선 (SMA)", value=f"${market_data['qqq_5sma']:.2f}")
with q3:
    diff_sma = market_data['qqq_5sma'] - market_data['qqq_20sma']
    st.metric(
        label="QQQ 20일선 (SMA)", 
        value=f"${market_data['qqq_20sma']:.2f}",
        delta=f"5일-20일 이격: ${diff_sma:+.2f}"
    )

st.divider()

# [그룹 3] 내 포트폴리오 현황
st.markdown("### 💼 내 계좌 현황")
p1, p2, p3 = st.columns(3)
with p1:
    total_val = input_qty * market_data['tqqq_close']
    st.metric(label="보유 자산 평가액", value=f"${total_val:,.2f}")
with p2:
    profit_pct = ((market_data['tqqq_close'] - input_avg) / input_avg) * 100
    st.metric(label="수익률", value=f"{profit_pct:+.2f}%")
with p3:
    st.metric(label="매수 평단가", value=f"${input_avg:.2f}", delta=f"보유 수량: {input_qty:,}주", delta_color="off")

st.divider()

# ---------------------------------------------------------
# 🚦 V6 전략 실시간 시그널 현황 (분류 정밀화)
# ---------------------------------------------------------
st.subheader("🚦 V6 전략 실시간 시그널 현황")
st.caption("시장 데이터를 실시간 분석하여 조건 포착 시 초록불(🟢), 미달성 시 빨간불(🔴)로 표시됩니다.")

s1, s2, s3 = st.columns(3)

with s1:
    st.markdown("### 🛒 매수 조건 (진입)")
    # 1단계: RSI 반등
    rsi_signal = "🟢 활성" if market_data['tqqq_rsi'] <= 35 else "🔴 비활성"
    st.write(f"• **1단계 (RSI 반등 구간)**: {rsi_signal}")
    
    # 2단계: QQQ 골든크로스
    gc_signal = "🟢 발생" if market_data['is_golden_cross'] else "🔴 비활성"
    st.write(f"• **2단계 (QQQ 골든크로스)**: {gc_signal}")
    
    # 3단계: TQQQ 200일선 돌파
    sma200_buy = "🟢 활성 (200일선 위)" if market_data['tqqq_close'] > market_data['tqqq_200sma'] else "🔴 비활성"
    st.write(f"• **3단계 (TQQQ 200일선 위)**: {sma200_buy}")

with s2:
    st.markdown("### 🚨 위험 관리 (대피)")
    # 200일선 하향 이탈 여부 (대피 조건)
    if market_data['tqqq_close'] < market_data['tqqq_200sma']:
        st.write("• **200일선 대피**: 🔴 **경고 (200일선 하향 이탈 ➔ SGOV 전량 대피)**")
    else:
        st.write("• **200일선 대피**: 🟢 **안전 (TQQQ 200일선 유지 중)**")

with s3:
    st.markdown("### 🎯 익절 조건 (SPYM 전환)")
    
    # 수익률 계산
    profit_pct = ((market_data['tqqq_close'] - input_avg) / input_avg) * 100 if input_avg > 0 else 0
    
    st.write(f"• **수익률 +50%**: {'🟢 달성' if profit_pct >= 50 else '🔴 미달성'}")
    st.write(f"• **수익률 +100%**: {'🟢 달성' if profit_pct >= 100 else '🔴 미달성'}")
    st.write(f"• **수익률 +150%**: {'🟢 달성' if profit_pct >= 150 else '🔴 미달성'}")
    st.write(f"• **수익률 +200%**: {'🟢 달성' if profit_pct >= 200 else '🔴 미달성'}")
    
    # QQQ 데드크로스 (단기 조정 시 15% 익절)
    dc_signal = "🟢 발생 (15% 매도 ➔ SPYM)" if market_data['is_dead_cross'] else "🔴 미발생"
    st.write(f"• **QQQ 데드크로스**: {dc_signal}")
    
    # RSI 과열 익절
    rsi80_signal = "🟢 과열 (20% 매도 ➔ SPYM)" if market_data['tqqq_rsi'] >= 80 else "🔴 미달성"
    st.write(f"• **TQQQ RSI 80 이상**: {rsi80_signal}")
st.divider()

# ---------------------------------------------------------
# 📝 매매 체크리스트 & 구글 시트 동기화 (200일선 대피 보완)
# ---------------------------------------------------------
st.subheader("📝 V6 매매 실행 체크리스트 (구글 시트 동기화)")

# 구글 시트에 sell_200sma 열이 없을 경우를 대비한 안전 체크
sell_200sma_val = bool(df_current.loc[0, "sell_200sma"]) if "sell_200sma" in df_current.columns else False

with st.form("checklist_form"):
    st.write("실제로 매매를 완료하셨다면 아래 항목을 체크하고 [구글 시트에 저장]을 눌러주세요.")
    
    # 리스크 관리 대피 경고 영역 (최상단 강조)
    st.markdown("##### 🚨 **위험 관리 (리스크 모드)**")
    chk_s200sma = st.checkbox("🚨 **TQQQ 200일선 하향 이탈 (전량 매도 ➔ SGOV 대피 완료)**", value=sell_200sma_val)
    st.divider()

    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("**[매수 실행]**")
        chk_b1 = st.checkbox("1단계 매수 완료 (20%)", value=bool(df_current.loc[0, "buy_1"]))
        chk_b2 = st.checkbox("2단계 매수 완료 (30%)", value=bool(df_current.loc[0, "buy_2"]))
        chk_b3 = st.checkbox("3단계 매수 완료 (50%)", value=bool(df_current.loc[0, "buy_3"]))

    with c2:
        st.markdown("**[익절 실행 ➔ SPYM 매수]**")
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
        "sell_200sma": chk_s200sma,
        "sell_50": chk_s50, "sell_100": chk_s100, "sell_150": chk_s150, "sell_200": chk_s200,
        "sell_dead": chk_sdead, "sell_rsi80": chk_srsi80, "sell_ath": chk_sath
    }])
    
    try:
        conn.update(worksheet="Sheet1", data=updated_df)
        st.toast("💾 구글 시트에 성공적으로 동기화되었습니다!", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")
