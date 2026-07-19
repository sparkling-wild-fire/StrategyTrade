# backtest/engine.py
import pandas as pd
import threading
from bisect import bisect_right
from factors import calculate_all
from strategies import score_stock
from sector import classify, get_sector_map
from sector_etf import _calc_etf_strength_from_hist, _classify_level, _load_sector_etf_map

_cache_lock = threading.Lock()


def run_single(code, hist_df, start_date=None, end_date=None,
               hold_days=10, min_hist=50, step=5,
               sector_map=None, etf_hist_map=None,
               sector_avg_return=None, sector_up_ratio=None, sector_vol_trend=None,
               sector_level=None, _sector_level_cache=None):
    if hist_df is None or len(hist_df) < min_hist + hold_days:
        return pd.DataFrame()

    hist_df = hist_df.copy()
    dates = hist_df['日期'].astype(str).tolist()
    n = len(dates)

    start_idx = min_hist
    end_idx = n - hold_days

    if start_date:
        candidates = [i for i in range(start_idx, end_idx) if dates[i] >= start_date]
        if candidates:
            start_idx = candidates[0]

    if end_date:
        candidates = [i for i in range(start_idx, end_idx) if dates[i] <= end_date]
        if candidates:
            end_idx = candidates[-1] + 1

    # 查个股所属板块
    if sector_map is None:
        sector_map = get_sector_map()
    stock_sector = classify(code, sector_map)

    # 预加载板块→ETF映射
    sector_etf_map = _load_sector_etf_map()

    # 预构建ETF排序日期列表（用bisect加速查找）
    etf_sorted_dates = {}
    if etf_hist_map:
        for etf_code, etf_df in etf_hist_map.items():
            etf_sorted_dates[etf_code] = etf_df['日期'].astype(str).tolist()

    # 板块强度缓存：同一日期+同一板块只算一次（可跨股票共享）
    if _sector_level_cache is not None:
        sector_level_cache = _sector_level_cache
    else:
        sector_level_cache = {}

    results = []

    for i in range(start_idx, end_idx, step):
        sub_df = hist_df.iloc[:i + 1].copy()

        df_ind = calculate_all(sub_df)
        if df_ind is None:
            continue

        # 动态判断该时间点的板块强度
        current_sector_level = sector_level
        if current_sector_level is None and etf_hist_map and stock_sector != '其他':
            current_date = dates[i]
            cache_key = f'{stock_sector}_{current_date}'

            if cache_key in sector_level_cache:
                current_sector_level = sector_level_cache[cache_key]
            else:
                etf_codes = sector_etf_map.get(stock_sector, [])
                best_strength = None
                for etf_code in etf_codes:
                    etf_df = etf_hist_map.get(etf_code)
                    if etf_df is None:
                        continue
                    sorted_d = etf_sorted_dates.get(etf_code, [])
                    cut_idx = bisect_right(sorted_d, current_date) - 1
                    if cut_idx < 20:
                        continue
                    etf_sub = etf_df.iloc[:cut_idx + 1]
                    strength = _calc_etf_strength_from_hist(etf_sub)
                    if strength is not None:
                        if best_strength is None or strength['return_20'] > best_strength['return_20']:
                            best_strength = strength
                current_sector_level = _classify_level(best_strength)
                with _cache_lock:
                    sector_level_cache[cache_key] = current_sector_level

        result = score_stock(
            df_ind,
            sector_avg_return=sector_avg_return,
            sector_up_ratio=sector_up_ratio,
            sector_vol_trend=sector_vol_trend,
            sector_level=current_sector_level,
        )
        if result is None:
            continue

        current_date = dates[i]
        current_close = float(hist_df['收盘'].iloc[i])
        future_close = float(hist_df['收盘'].iloc[min(i + hold_days, n - 1)])
        future_return = (future_close - current_close) / current_close

        # 计算MA20偏离度
        ma20_val = df_ind['MA20'].iloc[-1] if 'MA20' in df_ind.columns else None
        deviation = (current_close - ma20_val) / ma20_val if ma20_val and ma20_val > 0 else None

        results.append({
            '日期': current_date,
            '代码': code,
            '得分': result['total'],
            'MACD得分': result.get('macd_score', 0),
            'KDJ得分': result.get('kdj_score', 0),
            'BB得分': result.get('bb_score', 0),
            '量价得分': result.get('vol_score', 0),
            '追涨得分': result.get('chase_score', 0),
            '趋势得分': result.get('trend_score', 0),
            'RS得分': result.get('rs_score', 0),
            '评级': result['rating'],
            '仓位': result.get('position', '0%'),
            '板块类型': result.get('sector_type', ''),
            '建议持有': result.get('hold_suggestion', ''),
            '收盘价': current_close,
            'MA20偏离': round(deviation, 4) if deviation is not None else None,
            f'未来{hold_days}日收益': round(future_return, 4),
            '是否盈利': future_return > 0,
        })

    return pd.DataFrame(results)
