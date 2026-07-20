# factors/pattern.py — 量化K线形态因子
from factors.helpers import _calc_atr


def calculate(df):
    df['ATR_14'] = _calc_atr(df, period=14)


def score(df):
    score_val = 0
    details = []

    if len(df) < 5:
        return score_val, details

    o = df['开盘']
    h = df['最高']
    l = df['最低']
    c = df['收盘']
    atr = df['ATR_14']

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    curr_atr = atr.iloc[-1] if not atr.isna().iloc[-1] else 0

    # 辅助：实体和影线
    def body(row):
        return abs(row['收盘'] - row['开盘'])

    def upper_shadow(row):
        return row['最高'] - max(row['收盘'], row['开盘'])

    def lower_shadow(row):
        return min(row['收盘'], row['开盘']) - row['最低']

    def is_bullish(row):
        return row['收盘'] > row['开盘']

    def is_bearish(row):
        return row['收盘'] < row['开盘']

    # 近期趋势判断（5日涨跌幅）
    trend_5d = 0
    if len(df) >= 6:
        trend_5d = (c.iloc[-1] - c.iloc[-6]) / c.iloc[-6] if c.iloc[-6] > 0 else 0

    # ===== 看涨信号 =====

    # 早晨之星：大阴 + 小实体十字 + 大阳切入前阴50%以上
    if (is_bearish(prev2) and body(prev2) > 0.5 * curr_atr
            and body(prev) < 0.3 * body(prev2)
            and is_bullish(curr) and body(curr) > 0.5 * body(prev2)
            and curr['收盘'] > prev2['开盘'] + 0.5 * body(prev2)):
        score_val += 2
        details.append('早晨之星+2')

    # 看涨吞没：阳线实体完全包裹前阴实体，范围>1.2ATR
    if (is_bearish(prev) and is_bullish(curr)
            and curr['开盘'] <= prev['收盘'] and curr['收盘'] >= prev['开盘']
            and body(curr) > body(prev)
            and (h.iloc[-1] - l.iloc[-1]) > 1.2 * curr_atr):
        score_val += 2
        details.append('看涨吞没+2')

    # 锤子线：长下影线(>2倍实体)+小实体+出现在下跌末端
    if (lower_shadow(curr) > 2 * body(curr)
            and upper_shadow(curr) < body(curr)
            and body(curr) > 0
            and trend_5d < -0.02):
        score_val += 1
        details.append('锤子线+1')

    # 刺穿线：大阴后阳线低开但收盘深入阴线50%以上
    if (is_bearish(prev) and body(prev) > 0.5 * curr_atr
            and is_bullish(curr)
            and curr['开盘'] < prev['收盘']
            and curr['收盘'] > prev['开盘'] + 0.5 * body(prev)):
        score_val += 1
        details.append('刺穿线+1')

    # 红三兵：连续三根阳线且收盘逐步走高
    if (len(df) >= 3
            and is_bullish(prev2) and is_bullish(prev) and is_bullish(curr)
            and c.iloc[-1] > c.iloc[-2] > c.iloc[-3]
            and o.iloc[-1] > o.iloc[-2] > o.iloc[-3]):
        score_val += 1
        details.append('红三兵+1')

    # ===== 看跌信号 =====

    # 黄昏之星：大阳 + 小实体十字 + 大阴切入前阳50%以下
    if (is_bullish(prev2) and body(prev2) > 0.5 * curr_atr
            and body(prev) < 0.3 * body(prev2)
            and is_bearish(curr) and body(curr) > 0.5 * body(prev2)
            and curr['收盘'] < prev2['开盘'] - 0.5 * body(prev2)):
        score_val -= 2
        details.append('黄昏之星-2')

    # 看跌吞没：阴线实体完全包裹前阳实体
    if (is_bullish(prev) and is_bearish(curr)
            and curr['开盘'] >= prev['收盘'] and curr['收盘'] <= prev['开盘']
            and body(curr) > body(prev)):
        score_val -= 2
        details.append('看跌吞没-2')

    # 射击之星：长上影线+小实体+出现在上涨末端
    if (upper_shadow(curr) > 2 * body(curr)
            and lower_shadow(curr) < body(curr)
            and body(curr) > 0
            and trend_5d > 0.02):
        score_val -= 1
        details.append('射击之星-1')

    # 乌云盖顶：大阳后阴线高开但收盘深入阳线50%以下
    if (is_bullish(prev) and body(prev) > 0.5 * curr_atr
            and is_bearish(curr)
            and curr['开盘'] > prev['收盘']
            and curr['收盘'] < prev['开盘'] + 0.5 * body(prev)):
        score_val -= 1
        details.append('乌云盖顶-1')

    # 三只乌鸦：连续三根阴线且收盘逐步走低
    if (len(df) >= 3
            and is_bearish(prev2) and is_bearish(prev) and is_bearish(curr)
            and c.iloc[-1] < c.iloc[-2] < c.iloc[-3]
            and o.iloc[-1] < o.iloc[-2] < o.iloc[-3]):
        score_val -= 1
        details.append('三只乌鸦-1')

    return score_val, details
