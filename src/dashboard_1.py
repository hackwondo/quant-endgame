import duckdb
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import os
import base64
from datetime import datetime
from database import get_db_connection, get_db_connection_readonly

st.set_page_config(
    page_title="Quant Endgame - 논문 기반 무료 퀀트 스크리너",
    page_icon="🏛️",
    layout="wide"
)

# OG 메타태그 (카카오톡/블로그 공유 시 미리보기용)
st.markdown("""
<meta property="og:title" content="Quant Endgame - 아카데믹 퀀트 스크리너" />
<meta property="og:description" content="Jegadeesh(1993), Heston(2008), Fama-French(1993) 논문 기반 5대 전략으로 한국+미국 전 종목을 자동 스크리닝합니다. 무료 공개." />
<meta property="og:type" content="website" />
<meta property="og:url" content="https://quant-endgame.streamlit.app" />
<meta name="description" content="학술 논문 기반 무료 퀀트 스크리너. 12-1 모멘텀, 크로스섹션 계절성, 평균회귀, 거래량 이상, 저변동성 전략으로 한국+미국 전 종목 자동 분석." />
<meta name="keywords" content="퀀트,스크리너,모멘텀,계절성,RSI,무료,주식,종목분석,Quant,Screener" />
""", unsafe_allow_html=True)

# 1. 커스텀 CSS (단어 단위 줄바꿈 완벽 적용 & 심층 설명 박스 디자인)
st.markdown("""
<style>
    /* 한국어 글자 끊김 방지 (단어 단위 줄바꿈) */
    h1, h2, h3, h4, p, span, div {
        word-break: keep-all !important;
    }
    .metric-card {
        background-color: #F8F9FA; border: 1px solid #E9ECEF;
        border-radius: 12px; padding: 18px; margin-bottom: 15px;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.04);
    }
    .trend-card {
        background: linear-gradient(135deg, #F0FDF4 0%, #FFFFFF 100%);
        border: 2px solid #00D084;
    }
    .paper-box {
        background-color: #0F172A; color: #F8FAFC; padding: 24px;
        border-radius: 12px; border-left: 6px solid #00D084; margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1); line-height: 1.6;
    }
    .paper-title { font-size: 20px; font-weight: bold; color: #38BDF8; margin-bottom: 6px; }
    .paper-author { font-size: 13.5px; color: #94A3B8; margin-bottom: 16px; border-bottom: 1px dashed #334155; padding-bottom: 10px; }
    .sec-title { color: #FACC15; font-weight: bold; margin-top: 12px; margin-bottom: 4px; display: block; }
    .win-rate { font-size: 24px; font-weight: bold; color: #00D084; float: right; }
    .ticker-title { font-size: 18px; font-weight: bold; color: #212529; }
    .sub-info { font-size: 13px; color: #6C757D; margin-top: 8px; }
    
    .disclaimer-banner {
        background-color: #FEF2F2; border: 1px solid #FECACA; color: #991B1B;
        padding: 12px 18px; border-radius: 8px; font-size: 13px; margin-bottom: 18px;
    }
    .counter-box {
        background-color: #F1F5F9; border: 1px solid #CBD5E1; color: #334155;
        padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: bold;
        text-align: right; white-space: nowrap;
    }
</style>
""", unsafe_allow_html=True)

# ── Google AdSense 광고 설정 ──
# 🔑 아래 'ca-pub-XXXXXXXXXX'를 본인의 애드센스 게시자 ID로 교체하세요.
ADSENSE_PUB_ID = "ca-pub-XXXXXXXXXX"  # ← 여기에 본인 ID 입력

# 애드센스 헤더 스크립트 (페이지당 1회만 로드)
st.markdown(f"""
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_PUB_ID}"
     crossorigin="anonymous"></script>
""", unsafe_allow_html=True)

def show_ad(slot_id, ad_format="auto", style="display:block; text-align:center; margin: 16px 0;"):
    """구글 애드센스 광고 슬롯을 삽입합니다."""
    st.markdown(f"""
    <div style="{style}">
        <ins class="adsbygoogle"
             style="display:block"
             data-ad-client="{ADSENSE_PUB_ID}"
             data-ad-slot="{slot_id}"
             data-ad-format="{ad_format}"
             data-full-width-responsive="true"></ins>
        <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
    </div>
    """, unsafe_allow_html=True)
def update_and_get_visitors():
    # 먼저 쓰기 모드 시도 (수집 중이면 실패할 수 있음)
    try:
        conn = get_db_connection()
        today_str = datetime.today().strftime('%Y-%m-%d')
        exists = conn.execute("SELECT ViewCount FROM page_views WHERE VisitDate = ?", (today_str,)).fetchone()
        if exists:
            conn.execute("UPDATE page_views SET ViewCount = ViewCount + 1 WHERE VisitDate = ?", (today_str,))
        else:
            conn.execute("INSERT INTO page_views VALUES (?, 1)", (today_str,))
        today_views = conn.execute("SELECT ViewCount FROM page_views WHERE VisitDate = ?", (today_str,)).fetchone()[0]
        total_views = conn.execute("SELECT SUM(ViewCount) FROM page_views").fetchone()[0]
        conn.close()
        return today_views, total_views
    except Exception:
        pass
    # 쓰기 실패 시 읽기 전용으로 조회만
    try:
        conn = get_db_connection_readonly()
        today_str = datetime.today().strftime('%Y-%m-%d')
        today_views = conn.execute("SELECT ViewCount FROM page_views WHERE VisitDate = ?", (today_str,)).fetchone()
        today_views = today_views[0] if today_views else 0
        total_views = conn.execute("SELECT SUM(ViewCount) FROM page_views").fetchone()[0] or 0
        conn.close()
        return today_views, total_views
    except Exception:
        return 0, 0

def get_data_update_date():
    """DB 테이블의 LastUpdated에서 가장 최근 데이터 업데이트 날짜를 조회합니다."""
    try:
        conn = get_db_connection_readonly()
        result = conn.execute("SELECT MAX(LastUpdated) FROM quant_factors_cards").fetchone()[0]
        conn.close()
        if result:
            return pd.to_datetime(result).strftime('%Y-%m-%d')
    except Exception:
        pass
    return None

# 3. 로컬 PDF 뷰어 렌더러
_PAPERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'papers')

_GITHUB_PDF_BASE = "https://raw.githubusercontent.com/hackwondo/quant-endgame/main/papers"

def display_local_pdf(file_path):
    filename = os.path.basename(file_path)
    if not filename.lower().endswith('.pdf'):
        filename = filename + ".pdf"
    
    import urllib.parse
    raw_url = f"{_GITHUB_PDF_BASE}/{urllib.parse.quote(filename)}"
    viewer_url = f"https://mozilla.github.io/pdf.js/web/viewer.html?file={urllib.parse.quote(raw_url, safe='')}"
    st.markdown(
        f'<iframe src="{viewer_url}" width="100%" height="700" '
        f'style="border: 1px solid #CBD5E1; border-radius: 8px;"></iframe>',
        unsafe_allow_html=True
    )
# 4. 데이터 로딩
@st.cache_data(ttl=300)
def load_all_data():
    conn = get_db_connection_readonly()
    meta = conn.execute("SELECT * FROM tickers_meta").df()
    seas = conn.execute("SELECT * FROM seasonality_cards").df()
    mom = conn.execute("SELECT * FROM momentum_cards").df()
    factors = conn.execute("SELECT * FROM quant_factors_cards").df()
    conn.close()
    
    df = pd.merge(meta, factors, on='Ticker', how='inner')
    df = pd.merge(df, mom[['Ticker', 'MomentumScore', 'Recent1M_Return', 'Price12M_Ago', 'Price1M_Ago']], on='Ticker', how='left')
    df = pd.merge(df, seas[['Ticker', 'WinRate', 'AvgReturn', 'BuyDate', 'SellDate', 'HoldingDays', 'YearsCount']], on='Ticker', how='left')
    df['StockName'] = df['Name'].fillna(df['Ticker'])
    df['Sector'] = df['Sector'].fillna('기타')
    return df

def plot_seasonality_chart(ticker, stock_name, holding_days=30):
    try:
        conn = get_db_connection_readonly()
        df = conn.execute("SELECT Date, Close FROM daily_prices WHERE Ticker = ? ORDER BY Date ASC", (ticker,)).df()
        conn.close()
    except Exception:
        st.info("📊 일봉 데이터가 없어 차트를 표시할 수 없습니다. (클라우드 경량 모드)")
        return
    
    if df.empty: return
    df['Date'] = pd.to_datetime(df['Date'])
    
    # 분석할 타겟 기간 (예: 7월 1일 ~ 7월 13일)
    # 여기서는 매년 7/1 ~ 7/13 사이의 수익률을 계산합니다.
    target_m, start_d, end_d = 7, 1, 13
    
    yearly_returns = []
    for year in range(datetime.today().year - 10, datetime.today().year + 1):
        year_data = df[(df['Date'].dt.year == year) & (df['Date'].dt.month == target_m)]
        start_row = year_data[year_data['Date'].dt.day >= start_d]
        end_row = year_data[year_data['Date'].dt.day <= end_d]
        
        if not start_row.empty and not end_row.empty:
            p_start = start_row.iloc[0]['Close']
            p_end = end_row.iloc[-1]['Close']
            ret = ((p_end / p_start) - 1.0) * 100.0
            yearly_returns.append({'Year': year, 'Return': ret})
    
    # 데이터가 10년 미만일 경우 처리
    if len(yearly_returns) < 10:
        st.warning(f"⚠️ {stock_name} ({ticker})은 10년치 데이터가 부족합니다. (현재 {len(yearly_returns)}년치 데이터 보유)")
        st.markdown("### 📊 연도별 수익률: N/A")
        return

    # 막대그래프 시각화
    res_df = pd.DataFrame(yearly_returns)
    fig = go.Figure()
    colors = ['#EF4444' if r < 0 else '#00D084' for r in res_df['Return']]
    
    fig.add_trace(go.Bar(
        x=res_df['Year'], y=res_df['Return'],
        marker_color=colors,
        text=res_df['Return'].round(1).astype(str) + '%',
        textposition='outside'
    ))
    
    fig.update_layout(
        title=f"📊 {stock_name} ({ticker}) 과거 10년 동일 기간(7/1~7/13) 수익률",
        yaxis_title="수익률 (%)",
        xaxis_title="연도",
        template="plotly_white",
        height=400
    )
    fig.add_hline(y=0, line_color="gray", line_width=1)
    st.plotly_chart(fig, use_container_width=True)

# 5. 헤더 & 방문자 카운터 (비율을 4.5 : 1.5로 넉넉하게 넓혀서 줄바꿈 완벽 해결!)
today_v, total_v = update_and_get_visitors()
data_date = get_data_update_date()
date_label = f"📅 데이터 기준: {data_date}" if data_date else "📅 데이터 미수집"
st.markdown(f'<div class="counter-box">🔥 오늘 접속: <b>{today_v:,}명</b> | 누적: <b>{total_v:,}명</b> | {date_label}</div>', unsafe_allow_html=True)
st.title("🏛️ Quant Endgame: 아카데믹 퀀트 스크리너")

st.markdown("""
<div class="disclaimer-banner">
    ⚠️ <b>[법적 면책 및 투자 자문 안내]</b> 본 웹사이트에서 제공되는 모든 데이터, 통계 연산 및 논문 해설은 과거 주가 시계열에 기반한 학술 분석용 <b>소프트웨어 정보 제공 목적</b>이며, <b>자본시장법상 특정 종목에 대한 투자 자문이나 매수·매도 추천이 아닙니다.</b> 금융상품 투자는 원금 손실 위험이 있으며, 모든 매매 판단과 결과에 대한 최종 책임은 전적으로 투자자 본인에게 있습니다.
</div>
""", unsafe_allow_html=True)

# ── 📢 상단 배너 광고 (탭 위) ──
show_ad("1111111111")  # ← 애드센스에서 발급받은 광고 슬롯 ID로 교체

df = load_all_data()
st.sidebar.header("🔍 공통 스크리닝 필터")
selected_sectors = st.sidebar.multiselect("섹터 선택", options=sorted(df['Sector'].unique()), default=[])
search_query = st.sidebar.text_input("종목명/티커 검색", "")
if selected_sectors: df = df[df['Sector'].isin(selected_sectors)]
if search_query: df = df[df['StockName'].str.contains(search_query, case=False) | df['Ticker'].str.contains(search_query, case=False)]

# 6개 핵심 탭 구성
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚡ 12-1 모멘텀", "🟢 크로스섹션 계절성", "💧 단기 평균회귀", 
    "🔥 스마트머니 거래량", "🛡️ 저변동성 성장주", "📩 Contact & 약관"
])

# --- [TAB 1: 12-1 모멘텀] ---
with tab1:
    st.markdown("""
    <div class="paper-box">
        <div class="paper-title">📜 Returns to Buying Winners and Selling Losers: Implications for Market Efficiency (1993)</div>
        <div class="paper-author">Jegadeesh, N., & Titman, S. · <i>Journal of Finance</i>, 48(1), 65-91.</div>
        <span class="sec-title">💡 핵심 학술 원리 (Behavioral Finance Intuition)</span>
        일반 투자자들은 기업의 호재나 구조적인 실적 개선 뉴스에 대해 즉각 100% 반영하지 못하고 점진적으로 반응하는 <b>과소반응(Underreaction) 편향</b>을 보입니다. 또한 기관 투자자들은 이미 추세가 형성된 승자 종목을 분기 말 포트폴리오에 편입하려는 <b>군집 매매(Herding)</b>를 보입니다. 이로 인해 과거 3~12개월간 상위 수익률을 기록한 주식은 향후 수개월간 계속해서 오르는 강력한 관성(Momentum)을 갖게 됩니다.
        <span class="sec-title">⚙️ 실제 퀀트 연산 알고리즘 (Math & Formula)</span>
        본 스크리너는 전체 260거래일(약 1년) 데이터 중, 단기 매매 노이즈가 심한 <b>가장 최근 1개월(t-20 ~ t)을 의도적으로 소거</b>합니다. 최근 1개월 급등주는 차익실현 매물로 인한 미시구조적 평균회귀(Reversal) 가능성이 크기 때문입니다. 따라서 <b>과거 12개월 전 주가(t-250) 대비 1개월 전 주가(t-20)의 상승률</b>만을 계산하여 순수 중장기 추세 종목을 필터링합니다.
        <span class="sec-title">🎯 실전 매매 활용 가이드</span>
        대세 상승장이나 이동평균선이 정배열된 시장에서 가장 강력한 초과 수익(Alpha)을 냅니다. 단, 모멘텀 스코어가 높더라도 <b>'최근 1M 수익률'이 단기간에 +30% 이상 폭등</b>했다면 단기 과열 구간이므로 추격 매수를 자제하고 분할 진입하는 것이 안전합니다.
    </div>
    """, unsafe_allow_html=True)
    
    # 요청하신 정확한 파일명 연결 (jegadeesh-titman93.pdf)
    with st.expander("📖 [클릭] Jegadeesh & Titman (1993) 논문 PDF 원문 직접 열람하기"):
        display_local_pdf("../papers/jegadeesh-titman93.pdf")
        
    sub_df = df.dropna(subset=['MomentumScore']).sort_values('MomentumScore', ascending=False)
    
    st.markdown("""
    <div style="background: var(--secondary-background-color, #262730); border-left: 4px solid #3B82F6; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 0.9rem;">
        <b>📐 모멘텀 스코어 계산식:</b>&nbsp;&nbsp;
        <code style="background: #1E293B; padding: 3px 8px; border-radius: 4px; color: #60A5FA;">
        (1개월 전 주가 ÷ 12개월 전 주가 - 1) × 100
        </code><br>
        <span style="color: #94A3B8; margin-top: 6px; display: inline-block;">
        예) 성호전자 +4,000% → 12개월 전 100원이던 주가가 1개월 전 4,100원이 되었다는 뜻입니다.
        최근 1개월은 단기 노이즈(차익실현 매물) 제거를 위해 의도적으로 제외됩니다.
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    cols = st.columns(2)
    for idx, r in sub_df.head(20).reset_index().iterrows():
        with cols[idx % 2]:
            price_12m = f"{r['Price12M_Ago']:,.0f}" if pd.notna(r.get('Price12M_Ago')) else '-'
            price_1m = f"{r['Price1M_Ago']:,.0f}" if pd.notna(r.get('Price1M_Ago')) else '-'
            st.markdown(f'<div class="metric-card"><div><span class="ticker-title">{idx+1}. {r["StockName"]}</span><span class="win-rate">+{r["MomentumScore"]}%</span></div><div class="sub-info"><b>섹터:</b> {r["Sector"]} | 현재가: {r["CurrentPrice"]:,.0f}원 (최근 1M: {r["Recent1M_Return"]:+}%)<br>📊 12개월 전: {price_12m}원 → 1개월 전: {price_1m}원</div></div>', unsafe_allow_html=True)

# --- [TAB 2: 크로스섹션 계절성] ---
with tab2:
    st.markdown("""
    <div class="paper-box">
        <div class="paper-title">📜 Seasonality in the Cross-Section of Expected Stock Returns (2008)</div>
        <div class="paper-author">Heston, S. L., & Sadka, R. · <i>Journal of Financial Economics</i>, 87(2), 418-445.</div>
        <span class="sec-title">💡 핵심 학술 원리 (Calendar Anomaly)</span>
        주식시장에는 기업의 정기적인 실적 발표 주기(Earnings Seasonality), 배당 지급일, 연기금 및 기관 투자자의 연간/분기별 자금 집행 사이클 등 <b>캘린더 구조에 기인한 반복성</b>이 존재합니다. 논문에 따르면 주가 수익률은 정확히 연간 주기(12개월, 24개월, 36개월 전 등)로 유의미한 양(+)의 자기상관성(Autocorrelation)을 띱니다.
        <span class="sec-title">⚙️ 실제 퀀트 연산 알고리즘</span>
        과거 10년치 일봉 데이터 전체에서 <b>매년 오늘 날짜와 일치하는 기준일</b>을 추출한 뒤, 해당 매수일로부터 향후 30일(Holding Days) 동안 주가가 상승 마감했는지를 추적합니다. 10년간 시뮬레이션 중 상승한 횟수를 백분율로 나눈 <b>과거 승률(Win Rate)</b>과 <b>평균 기대 수익률(Avg Return)</b>을 산출합니다.
        <span class="sec-title">🎯 실전 매매 활용 가이드</span>
        과거 승률이 80~100%이면서 현재 주가가 <b>20일/60일 이동평균선 위에 위치해 추세까지 살아있는 종목</b>을 최우선 공략합니다. 아래 드롭다운 메뉴에서 종목을 선택해 연도별 주가 파도 차트를 반드시 대조해 보세요.
    </div>
    """, unsafe_allow_html=True)
    with st.expander("📖 [클릭] Heston & Sadka (2008) 논문 PDF 원문 직접 열람하기"):
        display_local_pdf("../papers/Heston_2008.pdf" if os.path.exists("../papers/Heston_2008.pdf") else "Quant_Academic_Papers_Reference.pdf")
    sub_df = df.dropna(subset=['WinRate']).sort_values(['WinRate', 'AvgReturn'], ascending=[False, False])
    opts = [f"{r['StockName']} ({r['Ticker']})" for _, r in sub_df.head(15).iterrows()]
    sel = st.selectbox("📊 심층 분석할 파도 차트 선택:", opts) if opts else None
    if sel: plot_seasonality_chart(sel.split(" (")[-1].replace(")",""), sel.split(" (")[0])
    cols = st.columns(2)
    for idx, r in sub_df.head(20).reset_index().iterrows():
        with cols[idx % 2]:
            st.markdown(f'<div class="metric-card"><div><span class="ticker-title">{idx+1}. {r["StockName"]}</span><span class="win-rate">{r["WinRate"]}%</span></div><div class="sub-info"><b>섹터:</b> {r["Sector"]} | 매수 {r["BuyDate"]} ~ {r["SellDate"]} (평균 {r["AvgReturn"]:+}%)</div></div>', unsafe_allow_html=True)

# --- [TAB 3: 단기 평균회귀 낙폭과대] ---
with tab3:
    st.markdown("""
    <div class="paper-box">
        <div class="paper-title">📜 Fads, Martingales, and Market Efficiency (1988)</div>
        <div class="paper-author">Bruce N. Lehmann · NBER Working Paper #2533</div>
        <span class="sec-title">💡 핵심 학술 원리 (Microstructure Liquidity Shock)</span>
        Bruce N. Lehmann은 1988년 NBER 워킹 페이퍼를 통해 주식시장의 단기 반전(Short-horizon reversal) 현상을 실증적으로 분석했습니다[cite: 4]. 시장 효율성 가설과 달리, 특정 주식들이 '승자(Winners)'와 '패자(Losers)'로 나뉘는 경향이 있으며, 이들은 다음 주에 강한 수익률 반전을 보이는 경향이 있음을 증명했습니다[cite: 4]. 이는 과소반응이나 단기 유동성 충격이 주가에 일시적인 왜곡을 만들기 때문입니다[cite: 4].
        <span class="sec-title">⚙️ 실제 퀀트 연산 알고리즘</span>
        본 스크리너는 Lehmann의 실증 연구를 따라, <b>최근 5일간 단기 수익률(Return 5D)이 -3% 이하로 급락</b>하고, 동시에 기술적 지표인 <b>14일 상대강도지수(RSI 14)가 40 이하로 하향 이탈</b>하여 극단적 과매도 구간에 진입한 종목들을 반등 기대치가 높은 순으로 필터링합니다.
        <span class="sec-title">🎯 실전 매매 활용 가이드</span>
        박스권이나 횡보장에서 유동성 공백을 이용한 V자 반등을 노리는 전략입니다. RSI가 30 이하로 내려간 우량주를 분할 매수할 때, 통계적으로 유의미한 평균회귀 수익을 기대할 수 있습니다.
    </div>
    """, unsafe_allow_html=True)
    
    # 논문 연결 (파일명: Fads_Martingales_and_Market_Efficiency.pdf)
    with st.expander("📖 [클릭] Lehmann (1988) 논문 원문 직접 열람하기"):
        display_local_pdf("../papers/Fads_Martingales_and_Market_Efficiency.pdf")
        
    sub_df = df[(df['Return_5D'] < -3.0) & (df['RSI_14'] <= 40.0)].sort_values('Return_5D', ascending=True)
    cols = st.columns(2)
    for idx, r in sub_df.head(20).reset_index().iterrows():
        with cols[idx % 2]:
            st.markdown(f'<div class="metric-card" style="border-left: 5px solid #EF4444;"><div><span class="ticker-title">{idx+1}. {r["StockName"]}</span><span class="win-rate" style="color:#EF4444;">{r["Return_5D"]:+}%</span></div><div class="sub-info"><b>섹터:</b> {r["Sector"]} | <b>RSI(14): {r["RSI_14"]}</b> | 현재가: {r["CurrentPrice"]:,.0f}원</div></div>', unsafe_allow_html=True)


# --- [TAB 4: 스마트머니 거래량 폭발] ---
with tab4:
    st.markdown("""
    <div class="paper-box">
        <div class="paper-title">📜 The High-Volume Return Premium (2001)</div><div class="paper-author">Gervais, S., Kaniel, R., & Mingelgrin, D. H. · <i>Journal of Finance</i>, 56(3), 877-919.</div>
        <span class="sec-title">💡 핵심 학술 원리 (Smart Money Accumulation)</span>
        주가는 조용하지만 평소 대비 비정상적으로 대량의 거래량이 터지는 현상은 단순 개인 투자자의 단타 매매가 아닌, <b>기관 투자자(Smart Money)의 거대 자금 매집이나 포지션 구축 신호</b>입니다. 거래량 충격을 동반한 주식은 투자자들의 가시성(Visibility)과 관심을 끌어모으며 향후 1~2개월 동안 시장을 유의미하게 아웃퍼폼합니다.
        <span class="sec-title">⚙️ 실제 퀀트 연산 알고리즘</span>
        당일 발생한 거래량을 <b>과거 60거래일간의 평균 거래량(Volume Mean 60D)</b>으로 나눈 배수(Volume Ratio)를 계산합니다. 평소 평균 거래량 대비 최소 2배 이상, 많게는 수배 폭발한 비정상 거래량 쇼크 종목만을 탐지합니다.
        <span class="sec-title">🎯 실전 매매 활용 가이드</span>
        바닥권에서 오랫동안 조용히 횡보하다가 <b>갑자기 거래량 배수가 2~5배 이상 터지는 종목</b>은 대시세 상승 초입 신호일 가능성이 매우 높습니다. 매수 후 거래량이 급감하며 숨 고르기를 할 때 2~3일간 분할 매수하는 타점이 훌륭합니다.
    </div>
    """, unsafe_allow_html=True)
    sub_df = df[df['Volume_Ratio'] >= 2.0].sort_values('Volume_Ratio', ascending=False)
    cols = st.columns(2)
    for idx, r in sub_df.head(20).reset_index().iterrows():
        with cols[idx % 2]:
            st.markdown(f'<div class="metric-card trend-card"><div><span class="ticker-title">{idx+1}. {r["StockName"]}</span><span class="win-rate">⚡ {r["Volume_Ratio"]}배 폭발</span></div><div class="sub-info"><b>섹터:</b> {r["Sector"]} | 당일 거래량: {r["CurrentVolume"]:,.0f}주</div></div>', unsafe_allow_html=True)

# --- [TAB 5: 저변동성 이상현상] ---
with tab5:
    st.markdown("""
    <div class="paper-box">
        <div class="paper-title">📜 Benchmarks as Limits to Arbitrage: Understanding the Low-Volatility Anomaly (2011)</div><div class="paper-author">Baker, M., Bradley, B., & Wurgler, J. · <i>Financial Analysts Journal</i>, 67(1), 40-54.</div>
        <span class="sec-title">💡 핵심 학술 원리 (Low-Volatility Anomaly)</span>
        "고위험 고수익(High Risk, High Return)"이라는 전통적 재무학 통념과 달리, 실제 주식시장에서는 개인 투자자들의 복권 선호 성향(투기주 매수)과 기관의 레버리지 제약으로 인해 <b>저변동성 주식이 고변동성 주식보다 위험 대비 훨씬 높은 장기 누적 수익률을 기록</b>하는 이상 현상이 증명되었습니다.
        <span class="sec-title">⚙️ 실제 퀀트 연산 알고리즘</span>
        과거 250일(약 1년) 동안 매일의 주가 변동률(일간 수익률 표준편차)을 계산한 뒤, 연간 기준($$\\sqrt{252}$$)으로 변환한 <b>연율화 변동성(Annual Volatility %)</b>을 산출합니다. 이 변동성 수치가 가장 낮고 조용한 최하위 종목 순으로 필터링합니다.
        <span class="sec-title">🎯 실전 매매 활용 가이드</span>
        거시경제가 불안하거나 금리 인상, 전쟁 이슈로 주식시장이 크게 출렁일 때 계좌를 방어해 주는 <b>최고의 하락장 방어 패치</b>입니다. 변동성이 10%대인 우량 성장주는 폭락장에서도 잘 버티며 장기 복리 마법을 만들어냅니다.
    </div>
    """, unsafe_allow_html=True)
    sub_df = df[(df['Volatility_250D'] > 0)].sort_values('Volatility_250D', ascending=True)
    cols = st.columns(2)
    for idx, r in sub_df.head(20).reset_index().iterrows():
        with cols[idx % 2]:
            st.markdown(f'<div class="metric-card"><div><span class="ticker-title">{idx+1}. {r["StockName"]}</span><span class="win-rate" style="color:#0EA5E9;">변동성 {r["Volatility_250D"]}%</span></div><div class="sub-info"><b>섹터:</b> {r["Sector"]} | 현재가: {r["CurrentPrice"]:,.0f}원</div></div>', unsafe_allow_html=True)

# --- [TAB 6: Contact Us & 약관] ---
with tab6:
    st.subheader("📩 Contact Us (제휴 및 사이트 이용 문의)")
    st.write("알고리즘 오류 제보, 학술 팩터 추가 제안 또는 광고 제휴 문의는 아래 폼을 이용해 주시기 바랍니다.")
    with st.form("contact_form"):
        c1, c2 = st.columns(2)
        with c1: name = st.text_input("성함 또는 기관명")
        with c2: email = st.text_input("답변 받으실 이메일 주소")
        category = st.selectbox("문의 유형", ["알고리즘/데이터 오류 제보", "구글 애드센스/광고 제휴 문의", "신규 논문 전략 추가 제안", "기타 일반 문의"])
        message = st.text_area("문의 상세 내용", height=120)
        submitted = st.form_submit_button("🚀 문의 내용 접수하기")
        if submitted: st.success(f"✅ {name}님의 문의가 접수되었습니다.")
            
    st.write("---")
    st.subheader("⚖️ 서비스 이용약관 및 개인정보처리방침 (Privacy Policy)")
    st.markdown("""
    1. **유사투자자문업 비해당 고지:** 본 서비스는 회원가입이나 유료 리딩을 유도하지 않으며, 투자자문이나 매매 시그널을 제공하지 않는 100% 자동 통계 시각화 툴입니다.
    2. **데이터 정확성 면책:** 한국거래소(KRX) 및 금융 데이터 프로바이더의 API 오류로 인해 시세 차이가 발생할 수 있으며, 개발사는 이로 인한 투자 손실에 어떠한 법적 책임도 지지 않습니다.
    3. **쿠키(Cookie) 및 광고 사용 고지:** 본 웹사이트는 구글 애드센스(Google AdSense) 광고 송출 및 트래픽 분석을 위해 사용자 쿠키를 수집할 수 있습니다.
    """)

# ── 📢 하단 광고 (페이지 최하단) ──
show_ad("2222222222")  # ← 애드센스에서 발급받은 광고 슬롯 ID로 교체