def score(df, sector_avg_return=None):
    """个股相对强度评分：个股20日涨幅 vs 板块均值"""
    score_val = 0
    details = []

    if len(df) < 20 or sector_avg_return is None:
        return score_val, details

    close = df['收盘']
    stock_return = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]

    if stock_return > sector_avg_return + 0.05:
        # 大幅跑赢板块：龙头股
        score_val += 2
        details.append(f'RS龙头+2(个股{stock_return:.1%}>板块{sector_avg_return:.1%})')
    elif stock_return > sector_avg_return:
        score_val += 1
        details.append(f'RS跑赢板块+1(个股{stock_return:.1%}>板块{sector_avg_return:.1%})')
    elif stock_return < sector_avg_return - 0.05:
        # 大幅跑输板块
        score_val -= 2
        details.append(f'RS大幅跑输-2(个股{stock_return:.1%}<板块{sector_avg_return:.1%})')
    elif stock_return < sector_avg_return:
        score_val -= 1
        details.append(f'RS跑输板块-1(个股{stock_return:.1%}<板块{sector_avg_return:.1%})')

    return score_val, details
