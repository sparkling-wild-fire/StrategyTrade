from factors import score_macd, score_kdj, score_boll, score_volume, score_chase, score_trend, score_rs

# 维度权重
WEIGHTS = {
    'macd': 1.0,
    'kdj': 0.8,
    'boll': 1.0,
    'volume': 0.8,
    'chase': 1.0,
    'trend': 1.0,
    'rs': 0.8,
}

# 追涨类信号（主升板块时放大，弱势板块时打折）
_MOMENTUM_FACTORS = {'macd', 'kdj', 'boll', 'trend'}


def _adjust_buy(score_val, factor):
    buy = max(score_val, 0)
    sell = score_val - buy
    return sell + int(buy * factor)


def _is_boll_squeezing(df):
    """判断布林带是否处于收口未突破状态（震荡市KDJ屏蔽条件）"""
    upper = df['BBU_20_2.0']
    lower = df['BBL_20_2.0']
    volume = df['成交量']

    if len(upper) < 20:
        return False

    bb_width = upper - lower
    min_width = bb_width.iloc[-20:].min()
    curr_width = bb_width.iloc[-1]
    vol_ratio = volume.iloc[-1] / volume.iloc[-5:].mean() if volume.iloc[-5:].mean() > 0 else 1

    squeezing = curr_width <= min_width * 1.1
    no_breakout = not (curr_width > bb_width.iloc[-2] and vol_ratio > 1.5)
    return squeezing and no_breakout


def score(df, sector_avg_return=None, sector_up_ratio=None, sector_vol_trend=None, sector_level=None):
    """量化评分主函数，返回综合得分和明细"""
    if len(df) < 35:
        return None

    macd_score, macd_details = score_macd(df)
    kdj_score, kdj_details = score_kdj(df)
    bb_score, bb_details = score_boll(df)
    vol_score, vol_details = score_volume(df)
    chase_score, chase_details = score_chase(df)
    trend_score, trend_details = score_trend(df)
    rs_score, rs_details = score_rs(df, sector_avg_return)

    # 震荡市KDJ屏蔽
    kdj_shielded = False
    if _is_boll_squeezing(df):
        kdj_score = 0
        kdj_details = ['震荡市KDJ屏蔽']
        kdj_shielded = True

    # 板块强度仅用于调整追涨因子权重，不单独作为评分因子
    # 主升持续中 → 适度放大；主升尾声 → 不放大；轮动 → 适度放大；弱势 → 大幅打折
    if sector_level == 'main':
        momentum_factor = 1.2
    elif sector_level == 'main_fading':
        momentum_factor = 1.0
    elif sector_level == 'weak':
        momentum_factor = 0.3
    else:
        momentum_factor = 1.2

    # 均线趋势过滤
    ma5 = df['MA5'].iloc[-1]
    ma10 = df['MA10'].iloc[-1]
    ma20 = df['MA20'].iloc[-1]
    bullish_align = ma5 > ma10 > ma20
    bearish_align = ma5 < ma10 < ma20

    if bearish_align:
        macd_score = _adjust_buy(macd_score, 0.5)
        kdj_score = _adjust_buy(kdj_score, 0.5)
        vol_score = _adjust_buy(vol_score, 0.5)
    elif bullish_align:
        macd_score = _adjust_buy(macd_score, 1.2)
        kdj_score = _adjust_buy(kdj_score, 1.2)
        vol_score = _adjust_buy(vol_score, 1.2)

    # 应用维度权重（追涨类因子受板块强度影响）
    weighted = {}
    raw_scores = {
        'macd': macd_score, 'kdj': kdj_score, 'boll': bb_score,
        'volume': vol_score, 'chase': chase_score, 'trend': trend_score,
        'rs': rs_score,
    }

    for key, val in raw_scores.items():
        w = WEIGHTS[key]
        if key in _MOMENTUM_FACTORS:
            w *= momentum_factor
        weighted[key] = int(val * w)

    total = sum(weighted.values())

    # 追高惩罚：按板块强度区分（主升板块追高有效，弱势板块追高风险大）
    close = df['收盘'].iloc[-1]
    ma20 = df['MA20'].iloc[-1]
    if ma20 > 0:
        deviation = (close - ma20) / ma20
        if sector_level == 'main':
            # 主升板块：追高是趋势确认，不惩罚
            all_details_extra = []
        elif sector_level == 'main_fading':
            # 主升尾声：轻微惩罚
            if deviation > 0.10:
                total -= 1
                all_details_extra = ['⚠偏离均线-1']
            else:
                all_details_extra = []
        elif sector_level == 'weak':
            # 弱势板块：严格限制追高
            if deviation > 0.10:
                total -= 2
                all_details_extra = ['⚠弱势追高-2']
            elif deviation > 0.06:
                total -= 1
                all_details_extra = ['⚠弱势偏离-1']
            else:
                all_details_extra = []
        else:
            # 轮动板块：适度限制
            if deviation > 0.06:
                total -= 1
                all_details_extra = ['⚠轮动偏离-1']
            else:
                all_details_extra = []
    else:
        all_details_extra = []

    # 买入质量校验：趋势或动量至少有一项为正，且负因子不超过2个
    has_trend = weighted['trend'] > 0 or bullish_align
    has_momentum = weighted['macd'] > 0
    neg_count = sum(1 for v in weighted.values() if v < 0)
    quality_ok = (has_trend or has_momentum) and neg_count <= 2

    all_details = (macd_details + kdj_details + bb_details + vol_details
                   + chase_details + trend_details + rs_details + all_details_extra)
    if kdj_shielded:
        all_details.append('⚠震荡市:KDJ屏蔽')
    if bearish_align:
        all_details.append('⚠空头排列:买入项×0.5')
    elif bullish_align:
        all_details.append('✅多头排列:买入项×1.2')
    if sector_level == 'main':
        all_details.append('🔥主升板块:追涨×1.2')
    elif sector_level == 'main_fading':
        all_details.append('⚠主升尾声:追涨×1.0')
    elif sector_level == 'weak':
        all_details.append('🔻弱势板块:追涨×0.3')

    # 综合评级（买入质量不达标时降档）
    if total >= 6 and quality_ok:
        rating = '强力买入'
    elif total >= 6 and not quality_ok:
        rating = '观望/试仓'
        all_details.append('⚠质量不足:降为观望')
    elif total >= 2:
        rating = '观望/试仓'
    elif total <= -5 and sector_level not in ('rotating', 'main', 'main_fading'):
        rating = '坚决卖出'
    else:
        rating = '中性'

    # 仓位映射
    if sector_level == 'main':
        if total >= 6:
            position = '60%'
        elif total >= 2:
            position = '30%'
        else:
            position = '0%'
    elif sector_level == 'main_fading':
        if total >= 6:
            position = '40%'
        elif total >= 2:
            position = '20%'
        else:
            position = '0%'
    else:
        if total >= 6:
            position = '50%'
        elif total >= 2:
            position = '20%'
        else:
            position = '0%'

    # 持有期建议
    if sector_level == 'main':
        hold_suggestion = '1~2月'
    elif sector_level == 'main_fading':
        hold_suggestion = '2~4周'
    elif sector_level == 'rotating':
        hold_suggestion = '2~4周'
    else:
        hold_suggestion = '1~2周'

    return {
        'total': total,
        'macd_score': weighted['macd'],
        'kdj_score': weighted['kdj'],
        'bb_score': weighted['boll'],
        'vol_score': weighted['volume'],
        'chase_score': weighted['chase'],
        'trend_score': weighted['trend'],
        'rs_score': weighted['rs'],
        'sector_score': 0,
        'rating': rating,
        'position': position,
        'hold_suggestion': hold_suggestion,
        'sector_type': sector_level or 'rotating',
        'details': all_details,
    }
