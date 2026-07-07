import duckdb
import os

DB_PATH_FULL = 'data/stock_data.duckdb'
DB_PATH_LIGHT = 'data/dashboard_light.duckdb'

def _get_db_path():
    """원본 DB가 있으면 원본, 없으면 경량 DB를 사용합니다."""
    if os.path.exists(DB_PATH_FULL):
        return DB_PATH_FULL
    return DB_PATH_LIGHT

def get_db_connection():
    os.makedirs('data', exist_ok=True)
    return duckdb.connect(_get_db_path())

def get_db_connection_readonly():
    """대시보드용 읽기 전용 커넥션 (수집/연산 중에도 동시 접근 가능)."""
    os.makedirs('data', exist_ok=True)
    return duckdb.connect(_get_db_path(), read_only=True)

def init_database():
    os.makedirs('data', exist_ok=True)
    conn = duckdb.connect(DB_PATH_FULL)  # 초기화는 항상 원본 DB에
    
    # 1. 일봉 원본 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            Ticker VARCHAR, Date DATE, Open DOUBLE, High DOUBLE,
            Low DOUBLE, Close DOUBLE, Volume BIGINT, Change DOUBLE,
            PRIMARY KEY (Ticker, Date)
        );
    """)
    
    # 2. 메타데이터 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers_meta (
            Ticker VARCHAR PRIMARY KEY, Name VARCHAR, Country VARCHAR,
            Sector VARCHAR, MarketCap BIGINT
        );
    """)
    
    # 3. [탭 2] 크로스섹션 계절성 (Heston 2008)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seasonality_cards (
            Ticker VARCHAR PRIMARY KEY, BuyDate VARCHAR, SellDate VARCHAR,
            HoldingDays INTEGER, WinRate DOUBLE, AvgReturn DOUBLE,
            YearsCount INTEGER, LastUpdated DATE
        );
    """)
    
    # 4. [탭 1] 12-1 중장기 모멘텀 (Jegadeesh 1993)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS momentum_cards (
            Ticker VARCHAR PRIMARY KEY, MomentumScore DOUBLE,
            Recent1M_Return DOUBLE, Price12M_Ago DOUBLE,
            Price1M_Ago DOUBLE, CurrentPrice DOUBLE, LastUpdated DATE
        );
    """)
    
    # 5. 멀티 팩터 테이블 (평균회귀, 거래량, 저변동성)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quant_factors_cards (
            Ticker VARCHAR PRIMARY KEY, Return_5D DOUBLE, RSI_14 DOUBLE,
            Volume_Ratio DOUBLE, Volatility_250D DOUBLE,
            CurrentPrice DOUBLE, CurrentVolume BIGINT, LastUpdated DATE
        );
    """)
    
    # 6. [신규 추가] 방문자 통계 카운터 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS page_views (
            VisitDate DATE PRIMARY KEY,
            ViewCount BIGINT
        );
    """)
    
    print("✅ 방문자 집계 카운터를 포함한 전체 DB 스키마 초기화 완료!")
    conn.close()

if __name__ == "__main__":
    init_database()