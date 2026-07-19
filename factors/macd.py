from factors.helpers import _recent_cross, _consecutive_change, _divergence


def calculate(df):
    df.ta.macd(append=True)


def score(df):
    score_val = 0
    details = []

    dif = df['MACD_12_26_9']
    dea = df['MACDs_12_26_9']
    hist = df['MACDh_12_26_9']
    curr = df.iloc[-1]

    golden, death = _recent_cross(dif, dea, lookback=3)

    # +2 零轴上方金叉（水上金叉）：DIF显著在零轴上方(>0.05)
    if golden and curr['MACD_12_26_9'] > 0.05 and curr['MACDs_12_26_9'] > 0:
        score_val += 2
        details.append('MACD零轴上方金叉+2')
    # +1 零轴附近金叉：DIF在-0.05~0.05之间
    elif golden and abs(curr['MACD_12_26_9']) <= 0.05 and hist.iloc[-1] > hist.iloc[-2]:
        score_val += 1
        details.append('MACD零轴附近金叉+1')

    # +1 DIF逼近零轴：|DIF|<0.01 且 HIST>0持续5天以上（即将金叉的强信号）
    if abs(curr['MACD_12_26_9']) < 0.01 and curr['MACDh_12_26_9'] > 0:
        recent_hist = hist.iloc[-5:]
        if (recent_hist > 0).all():
            score_val += 1
            details.append('MACD逼近零轴+1')

    # +1 持续正动能：HIST>0持续5天以上（上涨动能持续）
    if curr['MACDh_12_26_9'] > 0 and len(hist) >= 5:
        recent_hist = hist.iloc[-5:]
        if (recent_hist > 0).all() and 'MACD逼近零轴+1' not in details:
            score_val += 1
            details.append('MACD持续正动能+1')

    # +1 动能衰竭转强：hist连续3天递增 且 HIST已转正（零轴下方递增只是下跌减速）
    hist_increasing, hist_decreasing = _consecutive_change(hist)
    if hist_increasing and hist.iloc[-1] > 0:
        score_val += 1
        details.append('MACD动能衰竭转强+1')

    # +2 底背离：DIF<0 + 近30日跌幅>3% + 价格双底落差>1%（排除噪声）
    if _divergence(df['收盘'], hist, lookback=30, direction='bottom'):
        close_30 = df['收盘'].iloc[-30:]
        drop_pct = (close_30.iloc[0] - close_30.iloc[-1]) / close_30.iloc[0]
        p1 = close_30.iloc[:15].min()
        p2 = close_30.iloc[15:].min()
        low_diff = (p1 - p2) / p1
        if curr['MACD_12_26_9'] < 0 and drop_pct > 0.03 and low_diff > 0.01:
            score_val += 2
            details.append('MACD底背离+2')

    # -2 零轴上方死叉
    if death and curr['MACD_12_26_9'] > 0 and curr['MACDs_12_26_9'] > 0:
        score_val -= 2
        details.append('MACD零轴上方死叉-2')
    # -1 零轴下方死叉
    elif death and curr['MACD_12_26_9'] <= 0:
        score_val -= 1
        details.append('MACD下方死叉-1')

    # -1 动能衰退：hist连续3天递减
    if hist_decreasing:
        if 'MACD动能衰竭转强+1' not in details:
            score_val -= 1
            details.append('MACD动能衰退-1')

    # -1 零轴下方弱势：DIF<-0.01 且 DEA<0 且 HIST<0.02
    # （DIF在-0.01~0之间不算弱势，可能即将金叉）
    if curr['MACD_12_26_9'] < -0.01 and curr['MACDs_12_26_9'] < 0 and curr['MACDh_12_26_9'] < 0.02:
        score_val -= 1
        details.append('MACD零轴下方弱势-1')

    # -2 顶背离
    if _divergence(df['收盘'], hist, direction='top'):
        score_val -= 2
        details.append('MACD顶背离-2')

    return score_val, details
