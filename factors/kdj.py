from factors.helpers import _recent_cross, _divergence


def calculate(df):
    df.ta.stoch(k=9, d=3, slow_k=3, slow_d=3, append=True)
    df['J_9_3_3'] = 3 * df['STOCHk_9_3_3'] - 2 * df['STOCHd_9_3_3']


def score(df):
    score_val = 0
    details = []

    k = df['STOCHk_9_3_3']
    d = df['STOCHd_9_3_3']
    j = df['J_9_3_3']
    curr = df.iloc[-1]

    golden, death = _recent_cross(k, d, lookback=3)

    # +1 低位金叉（K<20时金叉）
    if golden and curr['STOCHk_9_3_3'] < 20:
        score_val += 1
        details.append('KDJ低位金叉+1')
    # +1 中位共振金叉（K在40-60区间金叉，J线向上拐头）
    elif golden and 40 <= curr['STOCHk_9_3_3'] <= 60 and j.iloc[-1] > j.iloc[-2]:
        score_val += 1
        details.append('KDJ中位共振金叉+1')

    # +1 底部背离
    if _divergence(df['收盘'], k, direction='bottom'):
        score_val += 1
        details.append('KDJ底部背离+1')

    # -1 高位死叉（K>80时死叉）
    if death and curr['STOCHk_9_3_3'] > 80:
        score_val -= 1
        details.append('KDJ高位死叉-1')

    # -1 J线极端值掉头（J>90后开始向下）
    if j.iloc[-2] > 90 and j.iloc[-1] < j.iloc[-2]:
        score_val -= 1
        details.append('KDJ_J线极端掉头-1')

    # -1 J线超买（J>100，极端超买追涨风险大）
    if j.iloc[-1] > 100:
        score_val -= 1
        details.append('KDJ_J线超买-1')

    # -2 顶部背离
    if _divergence(df['收盘'], k, direction='top'):
        score_val -= 2
        details.append('KDJ顶部背离-2')

    return score_val, details
