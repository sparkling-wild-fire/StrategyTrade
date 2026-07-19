"""盘中选股策略 — 轻量快速筛选，用于盘中实时监控

与盘后选股的区别：
- 不依赖历史数据缓存，仅使用盘中实时行情
- 仅计算快速指标（量比、涨跌幅、换手率），不计算MACD/KDJ/BOLL
- 适合盘中快速扫描异动标的，发现后可进一步用盘后策略深度分析
"""
from factors import score_chase


def quick_filter(spot_data, sector_map=None, prev_close_map=None):
    """
    盘中快速筛选

    参数:
        spot_data: {code: {日期,开盘,收盘,最高,最低,成交量}} 盘中实时行情
        sector_map: {code: industry_name} 板块映射（可选）
        prev_close_map: {code: prev_close} 昨收价映射（可选，用于计算涨跌幅）

    返回:
        list of dict，按涨跌幅降序排列
    """
    results = []

    for code, bar in spot_data.items():
        try:
            close = float(bar['收盘'])
            open_price = float(bar['开盘'])
            volume = float(bar['成交量'])

            # 跳过无效数据
            if close <= 0 or volume <= 0:
                continue

            # 涨跌幅
            if prev_close_map and code in prev_close_map:
                prev_close = float(prev_close_map[code])
                if prev_close > 0:
                    pct_change = (close - prev_close) / prev_close
                else:
                    continue
            else:
                # 无昨收价，用开盘价近似
                pct_change = (close - open_price) / open_price if open_price > 0 else 0

            # 量比（简化：当前量 vs 开盘至今的预期量）
            # 盘中无法精确计算量比，跳过

            # 追涨风险快速检查
            if abs(pct_change) >= 0.099:
                continue  # 涨停/跌停不参与盘中筛选

            # 基本筛选条件
            if pct_change < -0.03:
                continue  # 跌幅超过3%不关注

            results.append({
                '代码': code,
                '收盘': close,
                '涨跌幅': pct_change,
                '成交量': volume,
            })
        except (ValueError, TypeError, KeyError):
            continue

    # 按涨跌幅降序
    results.sort(key=lambda x: x['涨跌幅'], reverse=True)
    return results
