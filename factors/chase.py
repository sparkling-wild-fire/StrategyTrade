def score(df):
    score_val = 0
    details = []

    close = df['收盘']
    n = len(df)
    if n < 3:
        return score_val, details

    # 检查最近2天是否出现涨停/跌停
    for i in range(-2, 0):
        if n + i < 1:
            continue
        pct = (close.iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1]
        if pct >= 0.099:
            score_val -= 2
            details.append(f'追涨涨停{close.index[i] if hasattr(close.index[i], "strftime") else ""}-2')
            break

    for i in range(-2, 0):
        if n + i < 1:
            continue
        pct = (close.iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1]
        if pct <= -0.099:
            score_val -= 2
            details.append(f'恐慌跌停-2')
            break

    return score_val, details
