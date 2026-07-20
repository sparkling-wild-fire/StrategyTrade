# factors/chanlun.py — 缠论结构因子（分型/笔/中枢/背驰）


def _merge_inclusion(df):
    """处理K线包含关系，返回合并后的K线列表[(open, high, low, close), ...]"""
    merged = []
    for i in range(len(df)):
        o, h, l, c = df.iloc[i]['开盘'], df.iloc[i]['最高'], df.iloc[i]['最低'], df.iloc[i]['收盘']
        if not merged:
            merged.append([o, h, l, c])
            continue
        prev = merged[-1]
        # 包含关系：前K线完全包含当前K线 或 当前K线完全包含前K线
        if (prev[1] >= h and prev[2] <= l) or (h >= prev[1] and l <= prev[2]):
            # 合并：取前K线方向决定高低点
            if prev[3] >= prev[0]:  # 前K线向上
                new_h = max(prev[1], h)
                new_l = max(prev[2], l)
            else:  # 前K线向下
                new_h = min(prev[1], h)
                new_l = min(prev[2], l)
            prev[1] = new_h
            prev[2] = new_l
        else:
            merged.append([o, h, l, c])
    return merged


def _find_fractals(merged):
    """识别顶底分型，返回 [(index, type), ...]  type='top'/'bottom'"""
    fractals = []
    for i in range(1, len(merged) - 1):
        prev_h, prev_l = merged[i - 1][1], merged[i - 1][2]
        curr_h, curr_l = merged[i][1], merged[i][2]
        next_h, next_l = merged[i + 1][1], merged[i + 1][2]
        # 顶分型：中间K线高低点均最高
        if curr_h > prev_h and curr_h > next_h and curr_l > prev_l and curr_l > next_l:
            fractals.append((i, 'top'))
        # 底分型：中间K线高低点均最低
        elif curr_h < prev_h and curr_h < next_h and curr_l < prev_l and curr_l < next_l:
            fractals.append((i, 'bottom'))
    return fractals


def _find_bis(fractals, merged):
    """从分型中提取笔：相邻顶底分型连接，中间至少1根独立K线"""
    if len(fractals) < 2:
        return []
    bis = []
    last = fractals[0]
    for i in range(1, len(fractals)):
        curr = fractals[i]
        # 顶底交替 且 中间至少1根K线
        if last[1] != curr[1] and abs(curr[0] - last[0]) >= 2:
            direction = 'up' if last[1] == 'bottom' else 'down'
            bis.append({
                'from_idx': last[0],
                'to_idx': curr[0],
                'direction': direction,
                'from_price': merged[last[0]][2] if last[1] == 'bottom' else merged[last[0]][1],
                'to_price': merged[curr[0]][1] if curr[1] == 'top' else merged[curr[0]][2],
            })
            last = curr
    return bis


def _find_pivot(bis, merged):
    """找最近的中枢（至少3笔重叠区间）"""
    if len(bis) < 3:
        return None
    # 取最近5笔尝试找中枢
    recent = bis[-5:]
    for start in range(len(recent) - 2):
        segment = recent[start:start + 3]
        # 3笔的高低区间
        highs = []
        lows = []
        for bi in segment:
            from_i = bi['from_idx']
            to_i = bi['to_idx']
            bi_high = max(merged[from_i][1], merged[to_i][1])
            bi_low = min(merged[from_i][2], merged[to_i][2])
            highs.append(bi_high)
            lows.append(bi_low)
        overlap_high = min(highs)
        overlap_low = max(lows)
        if overlap_high > overlap_low:
            return {'high': overlap_high, 'low': overlap_low}
    return None


def calculate(df):
    """计算缠论结构，结果存入df属性（不存列，避免污染DataFrame）"""
    if len(df) < 10:
        return
    merged = _merge_inclusion(df)
    fractals = _find_fractals(merged)
    bis = _find_bis(fractals, merged)
    pivot = _find_pivot(bis, merged)
    # 存到df.attrs避免Pandas列警告
    df.attrs['chanlun'] = {
        'merged': merged,
        'fractals': fractals,
        'bis': bis,
        'pivot': pivot,
    }


def score(df):
    score_val = 0
    details = []

    chan = df.attrs.get('chanlun') if hasattr(df, 'attrs') else None
    if not chan or not chan.get('fractals'):
        return score_val, details

    fractals = chan['fractals']
    bis = chan['bis']
    pivot = chan['pivot']
    merged = chan['merged']

    # 底分型出现在下跌末端 → +1
    if len(fractals) >= 1:
        last_frac = fractals[-1]
        if last_frac[1] == 'bottom':
            # 判断是否在下跌末端：前面有顶分型且价格在下行
            if len(fractals) >= 2 and fractals[-2][1] == 'top':
                top_price = merged[fractals[-2][0]][1]
                bottom_price = merged[fractals[-1][0]][2]
                if top_price > bottom_price:
                    score_val += 1
                    details.append('缠论底分型+1')

    # 顶分型出现在上涨末端 → -1
    if len(fractals) >= 2:
        last_frac = fractals[-1]
        if last_frac[1] == 'top':
            if len(fractals) >= 2 and fractals[-2][1] == 'bottom':
                bottom_price = merged[fractals[-2][0]][2]
                top_price = merged[fractals[-1][0]][1]
                if top_price > bottom_price:
                    score_val -= 1
                    details.append('缠论顶分型-1')

    # 当前笔方向
    if bis:
        last_bi = bis[-1]
        if last_bi['direction'] == 'up':
            score_val += 1
            details.append('缠论向上笔+1')
        elif last_bi['direction'] == 'down':
            score_val -= 1
            details.append('缠论向下笔-1')

    # 中枢位置判断
    if pivot:
        curr_close = df['收盘'].iloc[-1]
        if curr_close > pivot['high']:
            score_val += 1
            details.append('缠论中枢上方+1')
        elif curr_close < pivot['low']:
            score_val -= 1
            details.append('缠论中枢下方-1')

    # 缠论背驰：价格创新低但MACD面积衰竭
    if len(df) >= 30 and 'MACDh_12_26_9' in df.columns:
        hist = df['MACDh_12_26_9']
        close = df['收盘']
        if len(close) >= 30 and len(hist) >= 30:
            # 前半段和后半段
            p1_low = close.iloc[-30:-15].min()
            p2_low = close.iloc[-15:].min()
            h1_area = abs(hist.iloc[-30:-15].sum())
            h2_area = abs(hist.iloc[-15:].sum())
            # 价格创新低但MACD面积缩小 = 底背驰
            if p2_low < p1_low and h2_area < h1_area * 0.8 and hist.iloc[-1] < 0:
                score_val += 2
                details.append('缠论底背驰+2')
            # 价格创新高但MACD面积缩小 = 顶背驰
            p1_high = close.iloc[-30:-15].max()
            p2_high = close.iloc[-15:].max()
            if p2_high > p1_high and h2_area < h1_area * 0.8 and hist.iloc[-1] > 0:
                score_val -= 2
                details.append('缠论顶背驰-2')

    return score_val, details
