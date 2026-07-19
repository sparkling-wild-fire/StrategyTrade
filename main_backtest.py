# main_backtest.py — 策略回测入口
import os
os.environ['TQDM_DISABLE'] = '1'

import sys
import time
import argparse
import pandas as pd
from market import fetch_stock_hist, prefetch_hist_batch
from sector import get_sector_map
from sector_etf import load_etf_hist_map
from backtest import run_single, run_batch, generate_report, print_report
from backtest.stoploss_engine import run_stoploss_backtest, run_stoploss_batch, print_stoploss_report

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
DEFAULT_CSV = os.path.join(OUTPUT_DIR, 'buy_signals.csv')


def load_codes_from_csv(csv_path):
    """从CSV文件读取证券代码列表，返回 [(code, name), ...]"""
    if not os.path.exists(csv_path):
        print(f"[ERROR] 文件不存在: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    if '代码' not in df.columns:
        print(f"[ERROR] CSV缺少'代码'列，当前列: {list(df.columns)}")
        sys.exit(1)

    codes = []
    for _, row in df.iterrows():
        code = str(row['代码']).strip().zfill(6)
        name = str(row.get('名称', code)).strip()
        codes.append((code, name))
    return codes


def run_backtest_codes(code_name_list, hold_days=10, step=10, min_hist=50, max_workers=3):
    """对给定代码列表执行回测"""
    total = len(code_name_list)
    print(f"\n[INFO] 准备回测 {total} 只证券（持有{hold_days}天，每{step}天采样）...\n")

    # 获取板块映射
    sector_map = get_sector_map()

    # 预加载板块ETF历史数据（用于动态判断各时间点的板块强度）
    etf_hist_map = load_etf_hist_map()

    # 预加载个股历史数据
    codes = [c for c, _ in code_name_list]
    prefetch_hist_batch(codes)

    # 获取历史数据
    code_hist_map = {}
    not_found = []
    for code, name in code_name_list:
        hist_df = fetch_stock_hist(code)
        if hist_df is not None and len(hist_df) >= min_hist + hold_days:
            code_hist_map[code] = hist_df
        else:
            not_found.append(f"{code} {name}")

    if not_found:
        print(f"[WARN] {len(not_found)} 只数据不足，跳过: {', '.join(not_found[:10])}"
              + (f' ...等{len(not_found)}只' if len(not_found) > 10 else ''))

    if not code_hist_map:
        print("[ERROR] 无有效数据，回测终止")
        return

    print(f"[INFO] 有效数据 {len(code_hist_map)} 只，开始回测...")
    print("[INFO] 板块强度：用截断ETF数据动态判断（无前视偏差）\n")

    start = time.time()

    # 全局板块强度缓存（跨股票共享，同板块同日期只算一次）
    global_sector_cache = {}
    cache_lock = __import__('threading').Lock()

    # 多线程回测
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_results = []
    done = 0
    max_workers = min(max_workers, 5)

    def _run_one(item):
        code, hist_df = item
        return run_single(
            code, hist_df, hold_days=hold_days, min_hist=min_hist, step=step,
            sector_map=sector_map, etf_hist_map=etf_hist_map,
            _sector_level_cache=global_sector_cache,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, item): item[0] for item in code_hist_map.items()}
        for f in as_completed(futures):
            done += 1
            try:
                result_df = f.result()
                if result_df is not None and not result_df.empty:
                    all_results.append(result_df)
            except Exception:
                pass
            if done % 50 == 0 or done == len(code_hist_map):
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(code_hist_map) - done) / rate if rate > 0 else 0
                print(f"  回测进度 {done}/{len(code_hist_map)} ({rate:.1f}只/s, ETA {eta:.0f}s)")

    elapsed = time.time() - start

    if not all_results:
        print("[WARN] 回测结果为空")
        return

    result_df = pd.concat(all_results, ignore_index=True)

    # 生成报告
    report = generate_report(result_df, hold_days=hold_days)
    print_report(report)
    print(f"\n  回测耗时: {elapsed:.1f}s")

    # 按板块类型统计
    _print_sector_type_stats(result_df, hold_days)

    # 保存结果
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, 'backtest_results.csv')
    result_df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"  详细结果已保存: {out_path}")

    # 按代码汇总
    summary = _summarize_by_code(result_df, hold_days)
    summary_path = os.path.join(OUTPUT_DIR, 'backtest_summary.csv')
    summary.to_csv(summary_path, index=False, encoding='utf-8-sig')
    print(f"  分证券汇总: {summary_path}")

    print(f"\n[OK] 回测完成")


def _print_sector_type_stats(result_df, hold_days):
    """按板块类型统计胜率"""
    ret_col = f'未来{hold_days}日收益'
    if '板块类型' not in result_df.columns:
        return

    print(f"\n--- 按板块类型统计 ---")
    type_names = {'main': '主升板块', 'main_fading': '主升尾声', 'rotating': '轮动板块', 'weak': '弱势板块'}
    for stype in ['main', 'main_fading', 'rotating', 'weak']:
        group = result_df[result_df['板块类型'] == stype]
        if len(group) == 0:
            continue
        win = group['是否盈利'].mean()
        avg = group[ret_col].mean()
        print(f"  {type_names.get(stype, stype)}: 样本{len(group)}  胜率{win:.1%}  平均收益{avg:.2%}")


def _summarize_by_code(result_df, hold_days):
    """按证券代码汇总回测结果"""
    ret_col = f'未来{hold_days}日收益'
    rows = []
    for code, group in result_df.groupby('代码'):
        win_rate = group['是否盈利'].mean()
        avg_ret = group[ret_col].mean()
        med_ret = group[ret_col].median()
        avg_score = group['得分'].mean()
        sector_type = group['板块类型'].mode().iloc[0] if '板块类型' in group.columns and len(group['板块类型'].mode()) > 0 else ''
        rows.append({
            '代码': code,
            '板块类型': sector_type,
            '样本数': len(group),
            '平均得分': round(avg_score, 2),
            '胜率': f'{win_rate:.1%}',
            '平均收益': f'{avg_ret:.2%}',
            '中位收益': f'{med_ret:.2%}',
            '最大收益': f'{group[ret_col].max():.2%}',
            '最大亏损': f'{group[ret_col].min():.2%}',
        })
    return pd.DataFrame(rows).sort_values('平均收益', ascending=False)


def run_stoploss(code_name_list, hold_days=20, step=5, min_hist=50, buy_threshold=2):
    """止损回测模式"""
    total = len(code_name_list)
    print(f"\n[INFO] 止损回测 {total} 只证券（买入阈值≥{buy_threshold}，最大持有{hold_days}天，-8%/跌破MA10止损）...\n")

    codes = [c for c, _ in code_name_list]
    prefetch_hist_batch(codes)

    code_hist_map = {}
    not_found = []
    for code, name in code_name_list:
        hist_df = fetch_stock_hist(code)
        if hist_df is not None and len(hist_df) >= min_hist + hold_days:
            code_hist_map[code] = hist_df
        else:
            not_found.append(f"{code} {name}")

    if not_found:
        print(f"[WARN] {len(not_found)} 只数据不足，跳过")

    if not code_hist_map:
        print("[ERROR] 无有效数据，回测终止")
        return

    print(f"[INFO] 有效数据 {len(code_hist_map)} 只，开始止损回测...\n")

    start = time.time()
    result_df = run_stoploss_batch(
        code_hist_map, buy_threshold=buy_threshold,
        hold_days=hold_days, step=step, min_hist=min_hist,
    )
    elapsed = time.time() - start

    if result_df is None or result_df.empty:
        print("[WARN] 回测结果为空")
        return

    print_stoploss_report(result_df)
    print(f"\n  回测耗时: {elapsed:.1f}s")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, 'stoploss_results.csv')
    result_df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"  详细结果已保存: {out_path}")
    print(f"\n[OK] 止损回测完成")


def load_etf_codes_from_db(sectors=None):
    """从etf_info表加载ETF代码列表，返回 [(code, name), ...]"""
    import pymysql
    from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset='utf8mb4',
    )
    try:
        cursor = conn.cursor()
        if sectors:
            placeholders = ','.join(['%s'] * len(sectors))
            cursor.execute(f"SELECT etf_code, etf_name, sector FROM etf_info WHERE sector IN ({placeholders})", sectors)
        else:
            cursor.execute("SELECT etf_code, etf_name, sector FROM etf_info")
        rows = cursor.fetchall()
    finally:
        conn.close()

    codes = []
    for etf_code, etf_name, sector in rows:
        code = str(etf_code).strip().zfill(6)
        name = str(etf_name).strip() if etf_name else code
        codes.append((code, name))
    return codes


def main():
    # ============ 回测参数（直接修改后点Run即可） ============
    MODE = 'etf'                    # 'csv'=从CSV文件读取, 'etf'=回测全部ETF, 'codes'=指定代码
    CODES = []                      # 指定证券代码，如 ['600048', '000001']；MODE='codes'时生效
    CSV_FILE = DEFAULT_CSV          # CSV文件路径；MODE='csv'时生效
    ETF_SECTORS = []                # 限定ETF板块，如 ['半导体', '创新药']；为空则全部ETF
    HOLD_DAYS = 10                  # 持有天数
    STEP = 10                       # 采样步长，5=每周 10=每两周
    MIN_HIST = 50                   # 最少历史天数
    MAX_WORKERS = 3                 # 并发线程数
    LIMIT = 50                    # 从CSV读取时最多回测只数（0=全部）
    STOPLOSS = False                # True=止损回测模式
    BUY_THRESHOLD = 2               # 止损回测时的买入阈值
    # ==========================================================

    if MODE == 'etf':
        code_name_list = load_etf_codes_from_db(sectors=ETF_SECTORS or None)
        total = len(code_name_list)
        if LIMIT > 0 and total > LIMIT:
            code_name_list = code_name_list[:LIMIT]
        sector_hint = f"板块{ETF_SECTORS}" if ETF_SECTORS else "全部"
        print(f"[模式] ETF回测: {sector_hint} ({total} 只)")
    elif MODE == 'codes':
        code_name_list = [(c.strip(), c.strip()) for c in CODES]
        print(f"[模式] 指定证券回测: {CODES}")
    else:
        code_name_list = load_codes_from_csv(CSV_FILE)
        total = len(code_name_list)
        if LIMIT > 0 and total > LIMIT:
            code_name_list = code_name_list[:LIMIT]
            print(f"[模式] 文件回测: {CSV_FILE} (共{total}只，取前{LIMIT}只)")
        else:
            print(f"[模式] 文件回测: {CSV_FILE} ({total} 只)")

    if STOPLOSS:
        run_stoploss(code_name_list, hold_days=HOLD_DAYS, step=STEP,
                     min_hist=MIN_HIST, buy_threshold=BUY_THRESHOLD)
    else:
        run_backtest_codes(
            code_name_list,
            hold_days=HOLD_DAYS,
            step=STEP,
            min_hist=MIN_HIST,
            max_workers=MAX_WORKERS,
        )


if __name__ == '__main__':
    main()
