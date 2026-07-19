# backtest/batch.py
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from backtest.engine import run_single


def run_batch(code_hist_map, hold_days=10, min_hist=50, step=5, max_workers=3):
    """
    批量回测

    参数:
        code_hist_map: {code: hist_df} 证券代码到历史数据的映射
        hold_days: 持有天数
        min_hist: 最少历史数据天数
        step: 采样步长
        max_workers: 并发线程数

    返回:
        DataFrame，所有证券的回测结果合并
    """
    all_results = []
    total = len(code_hist_map)
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for code, hist_df in code_hist_map.items():
            f = pool.submit(run_single, code, hist_df, hold_days=hold_days, min_hist=min_hist, step=step)
            futures[f] = code

        for f in as_completed(futures):
            code = futures[f]
            done += 1
            try:
                result_df = f.result()
                if result_df is not None and not result_df.empty:
                    all_results.append(result_df)
            except Exception as e:
                print(f"  [WARN] {code} 回测失败: {e}")

            if done % 10 == 0 or done == total:
                print(f"  回测进度 {done}/{total}")

    if all_results:
        return pd.concat(all_results, ignore_index=True)
    return pd.DataFrame()
