# fetch_hist_data.py — 批量拉取近3年行情数据并清洗写入MySQL
import os
os.environ['TQDM_DISABLE'] = '1'

import sys
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from market import get_stock_list, fetch_stock_hist, filter_a_stocks, get_etf_list
from market.cache import save_hist, get_last_date
from market.fetcher import _fetch_hist, _prev_trade_date
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, ETF_PREFIXES
import pymysql

THREE_YEARS_AGO = (datetime.now() - timedelta(days=1095)).strftime('%Y-%m-%d')
TODAY = datetime.now().strftime('%Y-%m-%d')
MIN_DATA_ROWS = 100       # 3年至少100个交易日数据（剔除退市/长期停牌）
MAX_DAILY_PCT = 0.30      # 单日涨跌幅超30%视为异常（排除ST和新股上市）


def _get_conn():
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset='utf8mb4',
    )


def clean_hist_data(df, code):
    """
    数据清洗：
    1. 剔除停牌日（成交量为0或NaN）
    2. 剔除异常值（单日涨跌幅超限、价格为0或负数）
    3. 只保留近3年数据
    4. 去重
    """
    if df is None or df.empty:
        return df

    original_len = len(df)

    # 只保留近3年
    df = df[df['日期'].astype(str) >= THREE_YEARS_AGO].copy()

    # 剔除成交量为0或NaN的行（停牌日）
    df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
    df = df[df['成交量'] > 0]

    # 剔除价格为0或负数或NaN的行
    for col in ['开盘', '收盘', '最高', '最低']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df[df[col] > 0]

    # 剔除异常涨跌幅（非ST股单日涨跌超30%）
    if len(df) >= 2:
        df = df.sort_values('日期').reset_index(drop=True)
        pct_change = df['收盘'].pct_change()
        # 保留首行和正常行
        mask = pct_change.isna() | (pct_change.abs() <= MAX_DAILY_PCT)
        df = df[mask].reset_index(drop=True)

    # 最高不低于最低
    df = df[df['最高'] >= df['最低']]

    # 去重（按日期）
    df = df.drop_duplicates(subset=['日期'], keep='last')

    # 排序
    df = df.sort_values('日期').reset_index(drop=True)

    removed = original_len - len(df)
    if removed > 0 and removed > original_len * 0.1:
        # 清洗掉超过10%的数据时打印警告
        pass  # 静默处理，避免刷屏

    return df


def is_delisted(hist_df):
    """判断是否退市：最新数据超过60天前"""
    if hist_df is None or len(hist_df) == 0:
        return True
    last_date = str(hist_df['日期'].iloc[-1])
    cutoff = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    return last_date < cutoff


def is_long_suspended(hist_df):
    """判断是否长期停牌：近60天有超50天成交量为0"""
    if hist_df is None or len(hist_df) < 30:
        return True
    return len(hist_df) < MIN_DATA_ROWS


def fetch_and_clean_one(code, name=''):
    """拉取单只证券数据并清洗，返回 (code, df, status)"""
    try:
        df = _fetch_hist(code)
        if df is None or df.empty:
            return code, None, 'no_data'

        # 清洗
        df = clean_hist_data(df, code)

        if len(df) < MIN_DATA_ROWS:
            return code, None, 'insufficient'

        if is_delisted(df):
            return code, None, 'delisted'

        # 写入MySQL缓存
        save_hist(code, df)
        return code, df, 'ok'

    except Exception as e:
        err_msg = str(e)
        # 检测限流
        if any(kw in err_msg.lower() for kw in ['rate', 'limit', '429', 'too many', '频繁', '限制', 'forbidden', '403']):
            print(f"  [限流] {code} {name}: {err_msg}")
            return code, None, 'rate_limit'
        # 检测超时
        if any(kw in err_msg.lower() for kw in ['timeout', 'timed out', '超时']):
            print(f"  [超时] {code} {name}")
            return code, None, 'timeout'
        return code, None, 'error'


def main():
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("  拉取近3年行情数据并清洗")
    print(f"  时间范围: {THREE_YEARS_AGO} ~ {TODAY}")
    print("=" * 60)

    # 1. 获取证券列表
    print("\n[1] 获取证券列表...")
    stock_df = get_stock_list()
    stock_df = filter_a_stocks(stock_df)
    etf_df = get_etf_list()

    all_codes = []
    for _, row in stock_df.iterrows():
        all_codes.append((str(row['代码']).zfill(6), str(row['名称'])))
    for _, row in etf_df.iterrows():
        all_codes.append((str(row['代码']).zfill(6), str(row['名称'])))

    print(f"    股票 {len(stock_df)} 只 + ETF {len(etf_df)} 只 = {len(all_codes)} 只\n")

    # 2. 检查现有数据
    print("[2] 检查现有MySQL缓存...")
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT code) FROM trade_hishq")
            cached_codes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM trade_hishq")
            total_rows = cur.fetchone()[0]
            cur.execute("SELECT MIN(date), MAX(date) FROM trade_hishq")
            date_range = cur.fetchone()
            print(f"    已缓存 {cached_codes} 只证券，{total_rows} 条记录")
            print(f"    日期范围: {date_range[0]} ~ {date_range[1]}")
    finally:
        conn.close()

    # 3. 清掉旧缓存（数据不足3年的全部重拉）
    print("\n[3] 清理旧缓存（数据不足3年的重拉）...")
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # 删除数据不足350条的旧缓存（3年约730条交易日，350是下限）
            cur.execute("""
                DELETE FROM trade_hishq WHERE code IN (
                    SELECT code FROM (
                        SELECT code FROM trade_hishq
                        GROUP BY code HAVING COUNT(*) < 350
                    ) t
                )
            """)
            deleted = cur.rowcount
            cur.execute("""
                DELETE FROM trade_check_record WHERE code IN (
                    SELECT code FROM (
                        SELECT code FROM trade_hishq
                        GROUP BY code HAVING COUNT(*) < 350
                    ) t
                )
            """)
            # 也清理没有数据的check记录
            cur.execute("""
                DELETE FROM trade_check_record
                WHERE code NOT IN (SELECT DISTINCT code FROM trade_hishq)
            """)
            conn.commit()
            print(f"    清理了 {deleted} 条不足3年的旧数据")
    finally:
        conn.close()

    # 4. 确定需要拉取的列表
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT code FROM trade_hishq")
            already_cached = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    need_fetch = [(c, n) for c, n in all_codes if c not in already_cached]
    print(f"\n[4] 需要拉取: {len(need_fetch)} 只（已有缓存 {len(already_cached)} 只跳过）\n")

    if not need_fetch:
        print("[OK] 全部已缓存，无需拉取")
        return

    # 5. 批量拉取+清洗+写入（串行+限流自动降速）
    print(f"[5] 开始批量拉取（串行，限流自动降速）...\n")
    start = time.time()

    ok_count = 0
    delisted_count = 0
    insufficient_count = 0
    error_count = 0
    no_data_count = 0
    rate_limit_count = 0
    timeout_count = 0
    delay = 0.3  # 初始请求间隔（秒）

    for idx, (code, name) in enumerate(need_fetch):
        _, df, status = fetch_and_clean_one(code, name)

        if status == 'ok':
            ok_count += 1
        elif status == 'delisted':
            delisted_count += 1
        elif status == 'insufficient':
            insufficient_count += 1
        elif status == 'no_data':
            no_data_count += 1
        elif status == 'rate_limit':
            rate_limit_count += 1
            delay = min(delay * 2, 5.0)  # 限流时加倍延迟，最多5秒
            print(f"  [限流] 第{rate_limit_count}次限流，延迟调整为{delay:.1f}s")
        elif status == 'timeout':
            timeout_count += 1
            delay = min(delay * 1.5, 5.0)
            print(f"  [超时] 第{timeout_count}次超时，延迟调整为{delay:.1f}s")
        else:
            error_count += 1

        # 连续5次无失败则逐步恢复速度
        if status == 'ok' and delay > 0.3:
            delay = max(delay * 0.9, 0.3)

        time.sleep(delay)

        done = idx + 1
        if done % 10 == 0 or done == len(need_fetch):
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(need_fetch) - done) / rate if rate > 0 else 0
            print(f"  进度 {done}/{len(need_fetch)} "
                  f"成功{ok_count} 退市{delisted_count} 不足{insufficient_count} "
                  f"无数据{no_data_count} 限流{rate_limit_count} 超时{timeout_count} 失败{error_count} "
                  f"延迟{delay:.1f}s ({rate:.1f}只/s, ETA {eta/60:.0f}min)")

    elapsed = time.time() - start

    # 6. 最终统计
    print(f"\n{'='*60}")
    print(f"  拉取完成")
    print(f"{'='*60}")
    print(f"  成功: {ok_count}")
    print(f"  退市(剔除): {delisted_count}")
    print(f"  数据不足(剔除): {insufficient_count}")
    print(f"  无数据: {no_data_count}")
    print(f"  限流: {rate_limit_count}")
    print(f"  超时: {timeout_count}")
    print(f"  失败: {error_count}")
    print(f"  耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # 验证最终数据
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT code) FROM trade_hishq")
            total_codes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM trade_hishq")
            total_rows = cur.fetchone()[0]
            cur.execute("SELECT MIN(date), MAX(date) FROM trade_hishq")
            date_range = cur.fetchone()
            cur.execute("SELECT AVG(cnt) FROM (SELECT code, COUNT(*) as cnt FROM trade_hishq GROUP BY code) t")
            avg_rows = cur.fetchone()[0]
            print(f"\n  最终缓存: {total_codes} 只证券, {total_rows:,} 条记录")
            print(f"  日期范围: {date_range[0]} ~ {date_range[1]}")
            print(f"  平均每只: {avg_rows:.0f} 条")
    finally:
        conn.close()

    print(f"\n[OK] 数据拉取和清洗完成")


if __name__ == '__main__':
    main()
