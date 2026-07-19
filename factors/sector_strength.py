def score(df, sector_avg_return=None, sector_up_ratio=None, sector_vol_trend=None, sector_level=None):
    """
    板块强度评分（已弃用作为评分因子，仅保留接口兼容）

    板块强度现在仅用于调整追涨类因子权重（在 aftermarket_strategy.py 中实现），
    不再单独作为评分维度，避免给已涨个股虚高加分。
    """
    return 0, []
