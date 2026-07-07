import FinanceDataReader as fdr
import pandas as pd
from database import get_db_connection

def update_all_tickers():
    conn = get_db_connection()
    
    # 0. 관리종목(KRX-ADMINISTRATIVE) 블랙리스트 수집
    print("🚫 관리종목 블랙리스트 수집 중...")
    try:
        admin_df = fdr.StockListing('KRX-ADMINISTRATIVE')
        # 컬럼명이 버전마다 다를 수 있으므로 안전 처리
        if 'Symbol' in admin_df.columns:
            blacklist = set(admin_df['Symbol'].tolist())
        elif 'Code' in admin_df.columns:
            blacklist = set(admin_df['Code'].tolist())
        else:
            blacklist = set(admin_df.iloc[:, 0].tolist())
        print(f"   ⛔ 관리종목 {len(blacklist)}개 제외 대상 확인")
    except Exception as e:
        print(f"   ⚠️ 관리종목 리스트 수집 실패 (필터 없이 진행): {e}")
        blacklist = set()
    
    # 1. 한국 주식 (KRX) 수집
    print("📥 한국 주식(KRX) 목록 수집 중...")
    krx_df = fdr.StockListing('KRX')
    krx_df['Ticker'] = krx_df['Code']
    krx_df['Sector'] = krx_df['Dept'].fillna('기타') if 'Dept' in krx_df.columns else '기타'
    krx_df['MarketCap'] = krx_df['Marcap'].fillna(0).astype(int) if 'Marcap' in krx_df.columns else 0
    krx_df['Country'] = 'Korea'
    meta_krx = krx_df[['Ticker', 'Name', 'Country', 'Sector', 'MarketCap']]
    
    # 관리종목 제외
    before_count = len(meta_krx)
    meta_krx = meta_krx[~meta_krx['Ticker'].isin(blacklist)]
    filtered = before_count - len(meta_krx)
    if filtered > 0:
        print(f"   ⛔ 관리종목 {filtered}개 제외 완료 (잔여 {len(meta_krx)}개)")
    
    # 2. 미국 주식 (S&P 500 + NASDAQ) 수집
    print("📥 미국 주식(S&P 500, NASDAQ) 목록 수집 중...")
    sp500_df = fdr.StockListing('S&P500')
    nasdaq_df = fdr.StockListing('NASDAQ')
    
    # 두 리스트 합치기 (중복 제거)
    us_df = pd.concat([sp500_df, nasdaq_df]).drop_duplicates(subset=['Symbol'])
    
    us_df['Ticker'] = us_df['Symbol']
    us_df['Sector'] = us_df['Industry'].fillna('기타') if 'Industry' in us_df.columns else '기타'
    us_df['MarketCap'] = 0  # FDR 미국 리스트엔 시총이 없으므로 기본값 0 처리
    us_df['Country'] = 'USA'
    meta_us = us_df[['Ticker', 'Name', 'Country', 'Sector', 'MarketCap']]
    
    # 3. 한국 + 미국 통합 적재
    final_meta = pd.concat([meta_krx, meta_us], ignore_index=True)
    
    conn.execute("INSERT OR REPLACE INTO tickers_meta SELECT * FROM final_meta")
    print(f"✅ 한국+미국 총 {len(final_meta)}개 종목 메타데이터 DB 적재 완료!")
    conn.close()

if __name__ == "__main__":
    update_all_tickers()