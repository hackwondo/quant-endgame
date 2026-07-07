"""
원본 DB에서 대시보드에 필요한 테이블만 추출하여 경량 DB를 생성합니다.
113MB → 2~3MB로 줄여서 GitHub에 올릴 수 있게 합니다.

사용법: python export_light_db.py
"""

import duckdb
import os

SRC_DB = os.path.join('src', 'data', 'stock_data.duckdb')
OUT_DB = os.path.join('src', 'data', 'dashboard_light.duckdb')

# 대시보드에서 실제로 쓰는 테이블만
TABLES = [
    'tickers_meta',
    'momentum_cards',
    'seasonality_cards',
    'quant_factors_cards',
    'page_views',
]

def export():
    if not os.path.exists(SRC_DB):
        print(f"❌ 원본 DB를 찾을 수 없습니다: {SRC_DB}")
        return
    
    # 기존 경량 DB 삭제
    if os.path.exists(OUT_DB):
        os.remove(OUT_DB)
    
    src = duckdb.connect(SRC_DB, read_only=True)
    dst = duckdb.connect(OUT_DB)
    
    for table in TABLES:
        try:
            df = src.execute(f"SELECT * FROM {table}").df()
            dst.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
            print(f"  ✅ {table}: {len(df):,}행")
        except Exception as e:
            print(f"  ⚠️ {table} 스킵: {e}")
    
    src.close()
    dst.close()
    
    size_mb = os.path.getsize(OUT_DB) / (1024 * 1024)
    print(f"\n📦 경량 DB 생성 완료: {OUT_DB} ({size_mb:.1f}MB)")

if __name__ == "__main__":
    export()
