"""
Quant Endgame - 전체 파이프라인 통합 실행 스크립트
하루에 한 번만 실행되며, 이미 완료했으면 자동 스킵합니다.

사용법:   python run_all.py           (자동 판단: 오늘 안 했으면 실행, 했으면 스킵)
         python run_all.py --force    (강제 재실행, 로그 무시)
         python run_all.py --calc-only (연산만 재실행, 중복 체크 없음)
"""

import time
import sys
import os
import json
from datetime import datetime

# ── 로그 파일 경로 ──
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', '.last_run.json')


def read_log():
    """마지막 실행 로그를 읽어옵니다."""
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_log(status, detail=""):
    """실행 결과를 로그에 기록합니다."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    log = {
        'date': datetime.today().strftime('%Y-%m-%d'),
        'finished_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': status,
        'detail': detail
    }
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def already_done_today():
    """오늘 이미 성공적으로 실행했는지 확인합니다."""
    log = read_log()
    if log is None:
        return False
    return log.get('date') == datetime.today().strftime('%Y-%m-%d') and log.get('status') == 'success'


def print_step(step_num, total, title):
    print(f"\n{'='*60}")
    print(f"  [{step_num}/{total}] {title}")
    print(f"{'='*60}")


def run_pipeline():
    args = sys.argv[1:]
    force = '--force' in args
    calc_only = '--calc-only' in args

    # ── 중복 실행 체크 (calc-only는 가볍게 돌리는 용도이므로 체크 안 함) ──
    if not force and not calc_only and already_done_today():
        log = read_log()
        print(f"\n⏭️  오늘({log['date']}) 이미 파이프라인 완료됨 — {log['finished_at']}")
        print(f"   강제 재실행하려면: python run_all.py --force")
        return

    total_steps = 2 if calc_only else 4
    current_step = 0
    pipeline_start = time.time()

    print(f"\n🚀 Quant Endgame 파이프라인 시작 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    mode = '연산만' if calc_only else ('강제 재실행' if force else '전체 실행')
    print(f"   모드: {mode}")

    # ── Step 1: DB 스키마 초기화 ──
    current_step += 1
    print_step(current_step, total_steps, "DB 스키마 초기화 (CREATE IF NOT EXISTS)")
    step_start = time.time()

    from database import init_database
    init_database()
    print(f"   ⏱️ 소요: {time.time() - step_start:.1f}초")

    if not calc_only:
        # ── Step 2: 메타데이터 업데이트 ──
        current_step += 1
        print_step(current_step, total_steps, "종목 메타데이터 업데이트 (KRX + S&P500 + NASDAQ)")
        step_start = time.time()

        try:
            from update_meta import update_all_tickers
            update_all_tickers()
        except Exception as e:
            print(f"   ⚠️ 메타 업데이트 실패 (기존 데이터로 계속 진행): {e}")

        print(f"   ⏱️ 소요: {time.time() - step_start:.1f}초")

        # ── Step 3: 일봉 데이터 수집 ──
        current_step += 1
        print_step(current_step, total_steps, "전 종목 일봉 데이터 병렬 수집 (10스레드)")
        step_start = time.time()

        from collector import run_parallel_collection
        run_parallel_collection()

        print(f"   ⏱️ 소요: {time.time() - step_start:.1f}초")

    # ── Step 4: 지표 연산 ──
    current_step += 1
    print_step(current_step, total_steps, "5대 핵심 지표 일괄 연산 (모멘텀/계절성/RSI/거래량/변동성)")
    step_start = time.time()

    from calculator import run_fast_quant_engine
    run_fast_quant_engine(holding_days=30)
    print(f"   ⏱️ 소요: {time.time() - step_start:.1f}초")

    # ── 완료 로그 기록 ──
    total_elapsed = time.time() - pipeline_start
    write_log('success', f"총 {total_elapsed:.1f}초 소요")

    print(f"\n{'='*60}")
    print(f"  ✅ 전체 파이프라인 완료!")
    print(f"  ⏱️ 총 소요 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
    print(f"  🕐 완료 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  💡 대시보드 실행: streamlit run dashboard.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_pipeline()