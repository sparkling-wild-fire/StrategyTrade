def calculate(df):
    df['MA5'] = df['收盘'].rolling(5).mean()
    df['MA10'] = df['收盘'].rolling(10).mean()
    df['MA20'] = df['收盘'].rolling(20).mean()


def score(df):
    score_val = 0
    details = []

    if len(df) < 20:
        return score_val, details

    curr = df.iloc[-1]
    close = curr['收盘']
    ma5 = curr['MA5']
    ma10 = curr['MA10']
    ma20 = curr['MA20']

    bullish = ma5 > ma10 > ma20
    bearish = ma5 < ma10 < ma20

    # +1 多头排列：MA5 > MA10 > MA20
    if bullish:
        score_val += 1
        details.append('TREND多头排列+1')

    # +1 价格站稳短期均线：收盘 > MA5（趋势延续确认）
    if close > ma5 and ma5 > ma20:
        score_val += 1
        details.append('TREND价格站稳均线+1')

    # +1 均线发散：(MA5-MA20)在扩大（趋势加速而非衰减）
    if bullish and len(df) >= 3:
        gap_now = ma5 - ma20
        gap_prev = df['MA5'].iloc[-3] - df['MA20'].iloc[-3]
        if gap_now > gap_prev > 0:
            score_val += 1
            details.append('TREND均线发散+1')

    # -1 空头排列：MA5 < MA10 < MA20
    if bearish:
        score_val -= 1
        details.append('TREND空头排列-1')

    # -1 价格跌破短期均线：收盘 < MA5 < MA20（趋势走弱）
    if close < ma5 and ma5 < ma20:
        score_val -= 1
        details.append('TREND价格跌破均线-1')

    return score_val, details
