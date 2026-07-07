import duckdb
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import get_db_connection
import threading
import time

# ── 설정 ──
MAX_WORKERS = 10       # 동시 수집 스레드 수 (너무 높이면 차단 위험, 10~20 권장)
BATCH_SIZE = 200       # 이만큼 모이면 DB에 한 번에 적재
SLEEP_PER_REQ = 0.05   # 요청 간 최소 대기 (초)

# 스레드 안전한 결과 수집용
_lock = threading.Lock()
_buffer = []           # 수집된 DataFrame 임시 저장
_stats = {'success': 0, 'skip': 0, 'fail': 0}


def fetch_one(ticker, start_date, today):
    """하나의 종목 데이터를 수집합니다 (스레드에서 실행)."""
    time.sleep(SLEEP_PER_REQ)
    
    if start_date > today:
        with _lock:
            _stats['skip'] += 1
        return None

    df = fdr.DataReader(ticker, start=start_date, end=today)
    
    if df is None or df.empty:
        with _lock:
            _stats['skip'] += 1
        return None

    df.reset_index(inplace=True)
    df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
    df['Ticker'] = ticker
    
    if 'Change' not in df.columns:
        df['Change'] = 0.0
        
    df = df[['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Change']]
    df['Date'] = pd.to_datetime(df['Date'])
    
    with _lock:
        _stats['success'] += 1
    
    return df


def flush_buffer(conn):
    """버퍼에 쌓인 데이터를 DB에 일괄 적재합니다."""
    global _buffer
    if not _buffer:
        return
    big_df = pd.concat(_buffer, ignore_index=True)
    conn.execute("INSERT OR REPLACE INTO daily_prices SELECT * FROM big_df")
    count = len(_buffer)
    _buffer = []
    return count


def get_all_last_dates(conn):
    """전 종목의 마지막 수집일을 한 번의 쿼리로 가져옵니다."""
    result = conn.execute(
        "SELECT Ticker, MAX(Date) as LastDate FROM daily_prices GROUP BY Ticker"
    ).df()
    last_dates = {}
    for _, row in result.iterrows():
        next_day = pd.to_datetime(row['LastDate']) + timedelta(days=1)
        last_dates[row['Ticker']] = next_day.strftime('%Y-%m-%d')
    return last_dates


def update_daily_prices(ticker):
    """단건 수집 (run_all.py 호환용 - 기존 인터페이스 유지)."""
    conn = get_db_connection()
    result = conn.execute(
        "SELECT MAX(Date) FROM daily_prices WHERE Ticker = ?", (ticker,)
    ).fetchone()[0]
    
    if result:
        start_date = (pd.to_datetime(result) + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        start_date = (datetime.today() - timedelta(days=3650)).strftime('%Y-%m-%d')
    
    today = datetime.today().strftime('%Y-%m-%d')
    
    if start_date > today:
        conn.close()
        return

    df = fdr.DataReader(ticker, start=start_date, end=today)
    
    if df is None or df.empty:
        conn.close()
        return

    df.reset_index(inplace=True)
    df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
    df['Ticker'] = ticker
    
    if 'Change' not in df.columns:
        df['Change'] = 0.0
        
    df = df[['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Change']]
    df['Date'] = pd.to_datetime(df['Date'])

    conn.execute("INSERT OR REPLACE INTO daily_prices SELECT * FROM df")
    conn.close()


def run_parallel_collection():
    """전 종목 병렬 수집 (run_all.py에서도 호출 가능)."""
    global _buffer, _stats
    _buffer = []
    _stats = {'success': 0, 'skip': 0, 'fail': 0}
    
    start_time = time.time()
    conn = get_db_connection()
    
    # 1) 전 종목 리스트 + 마지막 수집일 한 번에 로드
    tickers_df = conn.execute("SELECT Ticker, Name FROM tickers_meta").df()
    last_dates = get_all_last_dates(conn)
    
    today = datetime.today().strftime('%Y-%m-%d')
    ten_years_ago = (datetime.today() - timedelta(days=3650)).strftime('%Y-%m-%d')
    total_count = len(tickers_df)
    
    # 2) 수집 대상 목록 준비 (이미 최신인 종목은 사전 제거)
    tasks = []
    pre_skip = 0
    for _, row in tickers_df.iterrows():
        ticker = row['Ticker']
        start_date = last_dates.get(ticker, ten_years_ago)
        if start_date > today:
            pre_skip += 1
        else:
            tasks.append((ticker, row['Name'], start_date))
    
    if not tasks:
        print(f"⚡ 전 종목({total_count:,}개) 이미 최신 상태입니다!")
        conn.close()
        return
    
    print(f"🚀 총 {total_count:,}개 종목 중 {len(tasks):,}개 수집 대상 ({pre_skip:,}개 이미 최신)")
    print(f"   동시 {MAX_WORKERS}스레드 병렬 수집 시작!\n")
    
    # 3) 병렬 수집
    done_count = 0
    total_tasks = len(tasks)
    
    def progress_bar(current, total, width=30):
        filled = int(width * current / total) if total > 0 else 0
        bar = '█' * filled + '░' * (width - filled)
        pct = current / total * 100 if total > 0 else 0
        return f"[{bar}] {pct:5.1f}%"
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_one, ticker, start_date, today): (ticker, name)
            for ticker, name, start_date in tasks
        }
        
        for future in as_completed(future_map):
            ticker, name = future_map[future]
            done_count += 1
            elapsed = time.time() - start_time
            speed = done_count / elapsed if elapsed > 0 else 0
            eta = (total_tasks - done_count) / speed if speed > 0 else 0
            
            try:
                result_df = future.result()
                if result_df is not None:
                    rows = len(result_df)
                    _buffer.append(result_df)
                    print(f"   ✅ [{done_count:,}/{total_tasks:,}] {name}({ticker}) +{rows}건  "
                          f"{progress_bar(done_count, total_tasks)}  ⏱️ 남은 {eta:.0f}초")
                    
                    if len(_buffer) >= BATCH_SIZE:
                        flushed = flush_buffer(conn)
                        print(f"   💾 ──── {flushed}개 종목 DB 일괄 적재 완료 ────")
                else:
                    if done_count % 100 == 0:
                        print(f"   ⏭️  [{done_count:,}/{total_tasks:,}] 스킵 진행 중  "
                              f"{progress_bar(done_count, total_tasks)}")
                        
            except Exception as e:
                _stats['fail'] += 1
                print(f"   ❌ [{done_count:,}/{total_tasks:,}] {name}({ticker}) 실패: {e}")
    
    # 4) 잔여 버퍼 최종 적재
    if _buffer:
        flushed = flush_buffer(conn)
        print(f"   💾 ──── 잔여 {flushed}개 종목 DB 최종 적재 ────")
    
    conn.close()
    
    elapsed = time.time() - start_time
    speed = done_count / elapsed if elapsed > 0 else 0
    print(f"\n{'='*60}")
    print(f"  🎉 전 종목 수집 완료!")
    print(f"  ✅ 성공: {_stats['success']:,}개  ⏭️ 스킵: {_stats['skip'] + pre_skip:,}개  ❌ 실패: {_stats['fail']:,}개")
    print(f"  ⏱️ 소요: {elapsed:.1f}초 ({elapsed/60:.1f}분)  |  평균: {speed:.1f}건/초")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_parallel_collection()