from factors.helpers import _divergence


def calculate(df):
    pass


def score(df):
    score_val = 0
    details = []

    close = df['收盘']
    volume = df['成交量']

    # +1 量价配合：近5日上涨日放量、下跌日缩量
    if len(df) >= 6:
        recent = df.iloc[-5:]
        price_chg = recent['收盘'].diff().iloc[1:]
        vol_chg = recent['成交量'].diff().iloc[1:]
        up_mask = price_chg > 0
        down_mask = price_chg < 0
        up_vol_ok = (vol_chg[up_mask] > 0).all() if up_mask.any() else True
        down_vol_ok = (vol_chg[down_mask] < 0).all() if down_mask.any() else True
        if up_mask.any() and down_mask.any() and up_vol_ok and down_vol_ok:
            score_val += 1
            details.append('量价配合+1')

    # +1 缩量企稳：成交量萎缩至近20日地量附近
    if len(volume) >= 20:
        vol_20_min = volume.iloc[-20:].min()
        vol_20_mean = volume.iloc[-20:].mean()
        if volume.iloc[-1] <= vol_20_min * 1.2 and volume.iloc[-1] < vol_20_mean:
            score_val += 1
            details.append('缩量企稳+1')

    # -1 量价顶背离
    if _divergence(close, volume, lookback=10, direction='top'):
        score_val -= 1
        details.append('量价顶背离-1')

    # -1 放量滞涨
    if len(volume) >= 5:
        vol_ratio = volume.iloc[-1] / volume.iloc[-5:].mean() if volume.iloc[-5:].mean() > 0 else 1
        price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] if close.iloc[-2] > 0 else 0
        if vol_ratio > 1.5 and abs(price_change) < 0.01:
            score_val -= 1
            details.append('放量滞涨-1')

    return score_val, details
