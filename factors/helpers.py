def _calc_atr(df, period=14):
    """计算ATR（真实波幅均值），df需含 high/low/close 或 最高/最低/收盘 列"""
    high = df['最高'] if '最高' in df.columns else df['high']
    low = df['最低'] if '最低' in df.columns else df['low']
    close = df['收盘'] if '收盘' in df.columns else df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = tr1.to_frame('tr')
    tr['tr2'] = tr2
    tr['tr3'] = tr3
    tr_max = tr.max(axis=1)
    return tr_max.rolling(period).mean()


def _recent_cross(series_fast, series_slow, lookback=3):
    """检查最近lookback天内是否出现金叉/死叉，返回 (金叉, 死叉)"""
    golden = False
    death = False
    n = len(series_fast)
    start = max(1, n - lookback)
    for i in range(start, n):
        if series_fast.iloc[i] > series_slow.iloc[i] and series_fast.iloc[i-1] <= series_slow.iloc[i-1]:
            golden = True
        if series_fast.iloc[i] < series_slow.iloc[i] and series_fast.iloc[i-1] >= series_slow.iloc[i-1]:
            death = True
    return golden, death


def _consecutive_change(series, n=3):
    """检查序列末尾是否连续n天递增或递减，返回 (连续递增, 连续递减)"""
    if len(series) < n + 1:
        return False, False
    tail = series.iloc[-(n+1):]
    diffs = tail.diff().iloc[1:]
    increasing = (diffs > 0).all()
    decreasing = (diffs < 0).all()
    return increasing, decreasing


def _divergence(price_series, indicator_series, lookback=20, direction='bottom'):
    """
    检测背离
    direction='bottom': 价格创新低但指标未创新低（底背离）
    direction='top': 价格创新高但指标未创新高（顶背离）
    """
    if len(price_series) < lookback:
        return False
    p_recent = price_series.iloc[-lookback:]
    i_recent = indicator_series.iloc[-lookback:]

    if direction == 'bottom':
        p_min1 = p_recent.iloc[:lookback//2].min()
        p_min2 = p_recent.iloc[lookback//2:].min()
        i_min1 = i_recent.iloc[:lookback//2].min()
        i_min2 = i_recent.iloc[lookback//2:].min()
        return p_min2 < p_min1 and i_min2 >= i_min1
    else:
        p_max1 = p_recent.iloc[:lookback//2].max()
        p_max2 = p_recent.iloc[lookback//2:].max()
        i_max1 = i_recent.iloc[:lookback//2].max()
        i_max2 = i_recent.iloc[lookback//2:].max()
        return p_max2 > p_max1 and i_max2 <= i_max1
