import duckdb
import pandas as pd
import numpy as np
import time
from datetime import datetime
from database import get_db_connection

def run_fast_quant_engine(holding_days=30):
    start_time = time.time()
    print("🚀 [Step 1] 전체 일봉 데이터를 메모리로 한 번에 고속 로드합니다...")
    
    conn = get_db_connection()
    # 7,800번 조회하던 것을 단 1번의 쿼리로 메모리에 로드
    df_all = conn.execute("SELECT Ticker, Date, Close, Volume FROM daily_prices ORDER BY Ticker, Date ASC").df()
    
    if df_all.empty:
        print("❌ DB에 일봉 데이터가 없습니다. collector.py를 먼저 실행해 주세요.")
        conn.close()
        return

    df_all['Date'] = pd.to_datetime(df_all['Date'])
    today_m, today_d = datetime.today().month, datetime.today().day
    today_str = datetime.today().strftime('%Y-%m-%d')
    cur_year = datetime.today().year
    sell_date_str = (pd.to_datetime(f"{cur_year}-{today_m:02d}-{today_d:02d}") + pd.Timedelta(days=int(holding_days*1.4))).strftime('%m/%d')
    
    print(f"📊 [Step 2] 총 {df_all['Ticker'].nunique():,}개 종목 5대 핵심 지표 일괄 연산 중...")
    
    seas_list, mom_list, factors_list = [], [], []
    
    # 종목별 그룹화 가공 (DB I/O 없이 초고속 파이썬 메모리 연산)
    for ticker, group in df_all.groupby('Ticker'):
        n_len = len(group)
        if n_len < 65: continue
        
        closes = group['Close'].values
        volumes = group['Volume'].values
        dates = group['Date'].dt
        cur_price = closes[-1]
        cur_vol = volumes[-1]
        
        # ----------------------------------------------------
        # 1. [탭 1] 12-1 모멘텀 전략 연산
        # ----------------------------------------------------
        if n_len >= 252:  # 최소 1년(251거래일) + 여유 1일 확보 필수
            price_1m = closes[-21]   # t-20: 1개월 전 종가
            price_12m = closes[-251] # t-250: 12개월 전 종가
            if price_12m > 0 and price_1m > 0:
                mom_score = round(((price_1m / price_12m) - 1.0) * 100.0, 2)
                rec_1m = round(((cur_price / price_1m) - 1.0) * 100.0, 2)
                mom_list.append({
                    'Ticker': ticker, 'MomentumScore': mom_score, 'Recent1M_Return': rec_1m,
                    'Price12M_Ago': price_12m, 'Price1M_Ago': price_1m, 'CurrentPrice': cur_price,
                    'LastUpdated': today_str
                })
        
        # ----------------------------------------------------
        # 2. [탭 2] 크로스섹션 계절성 전략 연산 (수정된 코드)
        # ----------------------------------------------------
        if n_len >= 2520:  # 최소 10년치(252*10) 데이터 확보 → Heston(2008) 논문 기준
            group_seas = group.copy()
            group_seas['Future_Return'] = (group_seas['Close'].shift(-holding_days) / group_seas['Close'] - 1.0) * 100.0
            target = group_seas[group_seas['Date'].dt.month == today_m].copy()
            
            if not target.empty:
                target['Day_Diff'] = (target['Date'].dt.day - today_d).abs()
                
                # [수정] 그룹화 시 연도만 추출하고, Date 열과의 이름 충돌을 방지하기 위해 
                # yearly 결과에서 Date 열을 명시적으로 제거하거나 무시합니다.
                yearly = target.sort_values('Day_Diff').groupby(target['Date'].dt.year).first()
                
                # reset_index 시 Date 열이 겹치지 않도록 Date 열을 드롭하거나 
                # yearly 데이터프레임 구조를 더 깔끔하게 가져갑니다.
                if 'Date' in yearly.columns:
                    yearly = yearly.drop(columns=['Date'])
                
                yearly = yearly.reset_index() # 이제 인덱스(연도)만 열로 변환됩니다.
                
                valid = yearly.dropna(subset=['Future_Return'])
                if len(valid) >= 5:  # 최소 5년 이상 유효 데이터 필수 (10년 중 결측 허용)
                    win_rate = round((len(valid[valid['Future_Return'] > 0]) / len(valid)) * 100.0, 1)
                    avg_ret = round(valid['Future_Return'].mean(), 1)
                    seas_list.append({
                        'Ticker': ticker, 'BuyDate': f"{today_m:02d}/{today_d:02d}",
                        'SellDate': sell_date_str, 'HoldingDays': holding_days,
                        'WinRate': win_rate, 'AvgReturn': avg_ret,
                        'YearsCount': len(valid), 'LastUpdated': today_str
                    })
                    

        # ----------------------------------------------------
        # 3. [탭 3, 4, 5] 멀티 팩터 (평균회귀 / 거래량 / 저변동성)
        # ----------------------------------------------------
        price_5d = closes[-6] if n_len >= 6 else closes[0]
        ret_5d = round(((cur_price / price_5d) - 1.0) * 100.0, 2) if price_5d > 0 else 0.0
        
        # RSI 14 연산 (Wilder's Smoothing 방식 - 업계 표준)
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        
        if len(gains) >= 14:
            # Step 1: 첫 14일은 SMA로 시드값 계산
            avg_gain = np.mean(gains[:14])
            avg_loss = np.mean(losses[:14])
            # Step 2: 이후 Wilder's Exponential Smoothing 적용
            for i in range(14, len(gains)):
                avg_gain = (avg_gain * 13 + gains[i]) / 14.0
                avg_loss = (avg_loss * 13 + losses[i]) / 14.0
            # Step 3: RSI 산출 (avg_loss==0이면 전부 상승 → RSI 100)
            if avg_loss == 0:
                rsi_14 = 100.0
            else:
                rsi_14 = round(100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))), 1)
        else:
            rsi_14 = 50.0  # 데이터 부족 시 중립값
        
        # 거래량 배수
        vol_mean_60 = np.mean(volumes[-61:-1]) if n_len >= 61 else np.mean(volumes[:-1])
        vol_ratio = round(cur_vol / vol_mean_60, 2) if vol_mean_60 > 0 else 1.0
        
        # 연율화 변동성 (250거래일 미만이면 정확도 낮으므로 0 처리)
        if n_len >= 250:
            daily_rets = pd.Series(closes[-250:]).pct_change().dropna()
            vol_annual = round(daily_rets.std() * np.sqrt(252) * 100.0, 2)
            if pd.isna(vol_annual): vol_annual = 0.0
        else:
            vol_annual = 0.0  # 데이터 부족 → 저변동성 탭에서 자연 제외 (>0 필터)
        
        factors_list.append({
            'Ticker': ticker, 'Return_5D': ret_5d, 'RSI_14': rsi_14,
            'Volume_Ratio': vol_ratio, 'Volatility_250D': vol_annual,
            'CurrentPrice': cur_price, 'CurrentVolume': cur_vol,
            'LastUpdated': today_str
        })

    print("💾 [Step 3] 연산 완료! DB에 결과 테이블을 통째로 덮어씁니다 (Bulk Insert)...")
    
    # 7,800번 Insert 하던 것을 단 3번의 벌크 연산으로 완료
    if mom_list:
        mom_df = pd.DataFrame(mom_list)
        conn.execute("INSERT OR REPLACE INTO momentum_cards SELECT * FROM mom_df")
    if seas_list:
        seas_df = pd.DataFrame(seas_list)
        conn.execute("INSERT OR REPLACE INTO seasonality_cards SELECT * FROM seas_df")
    if factors_list:
        factors_df = pd.DataFrame(factors_list)
        conn.execute("INSERT OR REPLACE INTO quant_factors_cards SELECT * FROM factors_df")
        
    conn.close()
    elapsed = time.time() - start_time
    print(f"🎉 전 종목 고속 연산 완료! (소요 시간: 단 {elapsed:.2f}초)")

if __name__ == "__main__":
    run_fast_quant_engine()