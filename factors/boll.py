def calculate(df):
    df.ta.bbands(length=20, append=True)


def score(df):
    score_val = 0
    details = []

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    close = df['收盘']
    upper = df['BBU_20_2.0']
    mid = df['BBM_20_2.0']
    lower = df['BBL_20_2.0']
    volume = df['成交量']

    mid_trending_up = mid.iloc[-1] > mid.iloc[-3]

    # +1 中轨支撑企稳
    if mid_trending_up:
        near_mid = abs(curr['收盘'] - curr['BBM_20_2.0']) / curr['BBM_20_2.0'] <= 0.02
        above_mid = curr['收盘'] >= curr['BBM_20_2.0']
        stable_candle = curr['收盘'] >= curr['开盘']
        if near_mid and above_mid and stable_candle:
            score_val += 1
            details.append('BOLL中轨支撑企稳+1')

    # +2 极度收口后放量突破
    bb_width = upper - lower
    if len(bb_width) >= 20:
        min_width = bb_width.iloc[-20:].min()
        curr_width = bb_width.iloc[-1]
        prev_width = bb_width.iloc[-2]
        vol_ratio = volume.iloc[-1] / volume.iloc[-5:].mean() if volume.iloc[-5:].mean() > 0 else 1
        if curr_width <= min_width * 1.1 and curr_width > prev_width and vol_ratio > 1.5:
            if mid.iloc[-1] > mid.iloc[-2]:
                score_val += 2
                details.append('BOLL收口放量突破+2')

    # +1 下轨超跌反弹
    if mid_trending_up and prev['收盘'] < prev['BBL_20_2.0'] and curr['收盘'] >= curr['BBL_20_2.0']:
        score_val += 1
        details.append('BOLL下轨超跌反弹+1')

    # +1 上轨突破强势：收盘>=上轨 且 中轨上行（强势动量信号）
    if curr['收盘'] >= curr['BBU_20_2.0'] and mid_trending_up:
        score_val += 1
        details.append('BOLL上轨突破强势+1')

    # -2 跌破中轨
    if prev['收盘'] >= prev['BBM_20_2.0'] and curr['收盘'] < curr['BBM_20_2.0']:
        score_val -= 2
        details.append('BOLL跌破中轨-2')

    # -1 缩量假突破 / -1 放量滞涨回落
    if prev['收盘'] > prev['BBU_20_2.0'] and curr['收盘'] <= curr['BBU_20_2.0']:
        vol_ratio = volume.iloc[-2] / volume.iloc[-7:-2].mean() if volume.iloc[-7:-2].mean() > 0 else 1
        if vol_ratio < 1.0:
            score_val -= 1
            details.append('BOLL缩量假突破-1')
        elif vol_ratio >= 1.5:
            price_change = (prev['收盘'] - prev['开盘']) / prev['开盘'] if prev['开盘'] > 0 else 0
            if abs(price_change) < 0.02:
                score_val -= 1
                details.append('BOLL放量滞涨回落-1')

    # -1 开口向下张口
    if curr['收盘'] < curr['BBL_20_2.0'] and lower.iloc[-1] < lower.iloc[-2]:
        score_val -= 1
        details.append('BOLL开口向下张口-1')

    return score_val, details
