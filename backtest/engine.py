# backtest/engine.py
import pandas as pd
from factors import calculate_all
from strategies import score_stock
from sector import classify, get_sector_map
from sector_etf import _calc_etf_strength_from_hist, _classify_level, _load_sector_etf_map


def run_single(code, hist_df, start_date=None, end_date=None,
               hold_days=10, min_hist=50, step=5,
               sector_map=None, etf_hist_map=None,
               sector_avg_return=None, sector_up_ratio=None, sector_vol_trend=None,
               sector_level=None):
    """
    单只证券回测

    参数:
        code: 证券代码
        hist_df: 完整历史日线DataFrame
        start_date/end_date: 回测时间范围
        hold_days: 持有天数
        min_hist: 最少需要多少天历史数据
        step: 采样步长
        sector_map: 板块映射（用于查个股所属板块）
        etf_hist_map: ETF历史数据（用于动态判断板块强度）
        sector_avg_return/sector_up_ratio/sector_vol_trend: 板块统计（实盘用）
        sector_level: 板块等级（实盘用）
    """
    if hist_df is None or len(hist_df) < min_hist + hold_days:
        return pd.DataFrame()

    hist_df = hist_df.copy()
    dates = hist_df['日期'].astype(str).tolist()
    n = len(dates)

    # 确定回测范围
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

    # 预构建ETF日期索引（加速截取）
    etf_date_sets = {}
    if etf_hist_map:
        for etf_code, etf_df in etf_hist_map.items():
            etf_date_sets[etf_code] = etf_df['日期'].astype(str).tolist()

    results = []

    for i in range(start_idx, end_idx, step):
        sub_df = hist_df.iloc[:i + 1].copy()

        df_ind = calculate_all(sub_df)
        if df_ind is None:
            continue

        # 动态判断该时间点的板块强度（用截断的ETF数据，无前视偏差）
        current_sector_level = sector_level  # 优先用实盘传入的
        if current_sector_level is None and etf_hist_map and stock_sector != '其他':
            current_date = dates[i]
            etf_codes = sector_etf_map.get(stock_sector, [])
            best_strength = None
            for etf_code in etf_codes:
                etf_df = etf_hist_map.get(etf_code)
                if etf_df is None:
                    continue
                # 截取到当前日期
                etf_dates = etf_date_sets.get(etf_code, [])
                # 找到 <= current_date 的最大索引
                cut_idx = -1
                for j, d in enumerate(etf_dates):
                    if d <= current_date:
                        cut_idx = j
                    else:
                        break
                if cut_idx < 20:
                    continue
                etf_sub = etf_df.iloc[:cut_idx + 1]
                strength = _calc_etf_strength_from_hist(etf_sub)
                if strength is not None:
                    if best_strength is None or strength['return_20'] > best_strength['return_20']:
                        best_strength = strength
            current_sector_level = _classify_level(best_strength)

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

        results.append({
            '日期': current_date,
            '代码': code,
            '得分': result['total'],
            '评级': result['rating'],
            '仓位': result.get('position', '0%'),
            '板块类型': result.get('sector_type', ''),
            '建议持有': result.get('hold_suggestion', ''),
            '收盘价': current_close,
            f'未来{hold_days}日收益': round(future_return, 4),
            '是否盈利': future_return > 0,
        })

    return pd.DataFrame(results)
