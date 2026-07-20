from factors import score_macd, score_kdj, score_boll, score_volume, score_chase, score_trend, score_rs, score_pattern, score_chanlun

# 维度权重
WEIGHTS = {
    'macd': 1.0,
    'kdj': 0.8,
    'boll': 1.0,
    'volume': 0.8,
    'chase': 1.0,
    'trend': 1.0,
    'rs': 0.8,
    'pattern': 1.0,
    'chanlun': 0.8,
}

# 追涨类信号（主升板块时放大，弱势板块时打折）
_MOMENTUM_FACTORS = {'macd', 'kdj', 'boll', 'trend', 'pattern'}


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
    pattern_score, pattern_details = score_pattern(df)
    chanlun_score, chanlun_details = score_chanlun(df)

    # 震荡市KDJ屏蔽
    kdj_shielded = False
    if _is_boll_squeezing(df):
        kdj_score = 0
        kdj_details = ['震荡市KDJ屏蔽']
        kdj_shielded = True

    # 板块强度仅用于调整追涨因子权重，不单独作为评分因子
    # 主升=市场最强 → 适度放大；强势=本身强 → 适度放大；主升尾声 → 不放大；
    # 涨后回落/弱势 → 大幅打折；轮动 → 适度放大
    if sector_level == 'main':
        momentum_factor = 1.2
    elif sector_level == 'strong':
        momentum_factor = 1.1
    elif sector_level == 'main_fading':
        momentum_factor = 1.0
    elif sector_level in ('weak', 'falling_back'):
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
        'rs': rs_score, 'pattern': pattern_score, 'chanlun': chanlun_score,
    }

    for key, val in raw_scores.items():
        w = WEIGHTS[key]
        if key in _MOMENTUM_FACTORS:
            w *= momentum_factor
        weighted[key] = int(val * w)

    total = sum(weighted.values())

    # 过度确认惩罚：趋势完美+动量/突破高分叠加=已涨一大段后再确认，见顶信号
    # 数据验证：趋势=3+MACD=3 胜率25.9%，趋势=3+BB>=2+MACD<2 胜率34.6%
    # 三重叠加(趋势3+MACD>=2+BB>=2)胜率仅22%，加重惩罚
    overconfirm_penalty = False
    if weighted['trend'] >= 3:
        macd_high = weighted['macd'] >= 2
        boll_high = weighted['boll'] >= 2
        if macd_high and boll_high:
            total -= 2
            overconfirm_penalty = True
        elif macd_high or boll_high:
            total -= 1
            overconfirm_penalty = True

    # 追高惩罚：按板块强度区分（主升板块追高有效，弱势板块追高风险大）
    close = df['收盘'].iloc[-1]
    ma20 = df['MA20'].iloc[-1]
    if ma20 > 0:
        deviation = (close - ma20) / ma20
        if sector_level == 'main':
            # 主升板块：追高是趋势确认，不惩罚
            all_details_extra = []
        elif sector_level == 'strong':
            # 强势板块：追高基本有效，轻微限制
            if deviation > 0.10:
                total -= 1
                all_details_extra = ['⚠偏离均线-1']
            else:
                all_details_extra = []
        elif sector_level == 'main_fading':
            # 主升尾声：轻微惩罚
            if deviation > 0.10:
                total -= 1
                all_details_extra = ['⚠偏离均线-1']
            else:
                all_details_extra = []
        elif sector_level in ('weak', 'falling_back'):
            # 弱势/涨后回落：严格限制追高
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

    # 共振加分：缠论底分型 + K线看涨形态 + 放量 → 额外+2
    resonance_bonus = 0
    has_chanlun_bottom = any('底分型' in d for d in chanlun_details)
    has_bullish_pattern = pattern_score >= 2
    has_volume = vol_score > 0
    if has_chanlun_bottom and has_bullish_pattern and has_volume:
        resonance_bonus = 2
        total += 2

    all_details = (macd_details + kdj_details + bb_details + vol_details
                   + chase_details + trend_details + rs_details
                   + pattern_details + chanlun_details + all_details_extra)
    if overconfirm_penalty:
        all_details.append('⚠趋势+MACD过度确认-1')
    if kdj_shielded:
        all_details.append('⚠震荡市:KDJ屏蔽')
    if bearish_align:
        all_details.append('⚠空头排列:买入项×0.5')
    elif bullish_align:
        all_details.append('✅多头排列:买入项×1.2')
    if sector_level == 'main':
        all_details.append('🔥主升板块:追涨×1.2')
    elif sector_level == 'strong':
        all_details.append('📈强势板块:追涨×1.1')
    elif sector_level == 'main_fading':
        all_details.append('⚠主升尾声:追涨×1.0')
    elif sector_level == 'falling_back':
        all_details.append('🔻涨后回落:追涨×0.3')
    elif sector_level == 'weak':
        all_details.append('🔻弱势板块:追涨×0.3')
    if resonance_bonus:
        all_details.append('🔥缠论+形态+放量共振+2')

    # 综合评级（买入质量不达标时降档）
    if total >= 6 and quality_ok:
        rating = '强力买入'
    elif total >= 6 and not quality_ok:
        rating = '观望/试仓'
        all_details.append('⚠质量不足:降为观望')
    elif total >= 2:
        rating = '观望/试仓'
    elif total <= -5 and sector_level not in ('rotating', 'main', 'strong', 'main_fading'):
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
    elif sector_level == 'strong':
        if total >= 6:
            position = '50%'
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
    elif sector_level == 'strong':
        hold_suggestion = '2~4周'
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
        'pattern_score': weighted['pattern'],
        'chanlun_score': weighted['chanlun'],
        'sector_score': 0,
        'rating': rating,
        'position': position,
        'hold_suggestion': hold_suggestion,
        'sector_type': sector_level or 'rotating',
        'details': all_details,
    }
