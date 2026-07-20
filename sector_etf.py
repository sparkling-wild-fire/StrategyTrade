# sector_etf.py — 用板块ETF判断当前主升板块
from market import fetch_stock_hist, get_etf_list
from sector import JQ_L1_TO_SECTOR

# 主升判定阈值
_MAIN_RALLY_RETURN = 0.06   # 15日涨幅>6%
_MAIN_RALLY_VOL_RATIO = 1.0  # 近5日均量 ≥ 近15日均量
_MAIN_RALLY_BULLISH = True   # 必须均线多头排列
_STRENGTH_PERIOD = 15        # 强度计算周期（日）

# 缓存
_etf_df_cache = None
_sector_etf_map_cache = None


def _get_etf_df():
    """获取ETF列表（带缓存）"""
    global _etf_df_cache
    if _etf_df_cache is None:
        _etf_df_cache = get_etf_list()
    return _etf_df_cache


def _calc_etf_strength_from_hist(hist_df):
    """从ETF历史数据计算趋势强度（截取到某一天的数据即可用于回测）"""
    p = _STRENGTH_PERIOD
    if hist_df is None or len(hist_df) < p:
        return None

    close = hist_df['收盘']
    volume = hist_df['成交量']

    ret = (close.iloc[-1] - close.iloc[-p]) / close.iloc[-p]
    vol_5 = volume.iloc[-5:].mean()
    vol_p = volume.iloc[-p:].mean()
    vol_ratio = vol_5 / vol_p if vol_p > 0 else 1

    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    bullish_align = ma5 > ma10 > ma20

    is_main_rally = (ret > _MAIN_RALLY_RETURN
                     and vol_ratio > _MAIN_RALLY_VOL_RATIO
                     and bullish_align)

    # 主升衰竭判定：均线还多头但量能萎缩或近5日涨幅放缓
    is_fading = False
    if bullish_align and ret > _MAIN_RALLY_RETURN:
        ret_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if len(close) >= 5 else 0
        if vol_ratio < 0.9 or ret_5 < ret * 0.2:
            is_fading = True

    return {
        'return': ret,
        'vol_ratio': vol_ratio,
        'bullish_align': bullish_align,
        'is_main_rally': is_main_rally,
        'is_fading': is_fading,
    }


def _classify_level(strength, is_market_best=False):
    """根据ETF强度信息分级
    main: 市场最强板块 且 本身强度高（涨幅>6%+量能+多头排列）
    strong: 本身强度高（涨幅>6%+多头排列）但不是市场最强
    main_fading: 主升衰竭
    rotating: 温和上涨
    weak: 弱势
    """
    if strength is None:
        return 'weak'
    if strength['is_main_rally'] and is_market_best:
        return 'main'
    if strength['is_main_rally']:
        return 'strong'
    if strength.get('is_fading'):
        return 'main_fading'
    if strength['return'] > 0.02 and strength['bullish_align']:
        return 'rotating'
    if strength['return'] > 0.03:
        return 'rotating'
    return 'weak'


def _calc_etf_strength(etf_code):
    """计算单只ETF当前的趋势强度"""
    hist = fetch_stock_hist(etf_code, use_cache=True)
    return _calc_etf_strength_from_hist(hist)


def _load_sector_etf_map():
    """从数据库加载 {板块: [etf_code, ...]} 映射（带缓存）"""
    global _sector_etf_map_cache
    if _sector_etf_map_cache is not None:
        return _sector_etf_map_cache

    df = _get_etf_df()
    sector_etf = {}
    for _, row in df.iterrows():
        sector = str(row.get('所属板块', '')).strip() if '所属板块' in df.columns else ''
        if not sector or sector in ('宽基', '红利', '策略', '区域', '央企'):
            continue
        code = str(row['代码']).strip().zfill(6)
        sector_etf.setdefault(sector, []).append(code)
    _sector_etf_map_cache = sector_etf
    return sector_etf


def get_sector_strength():
    """获取各板块当前强度（基于板块ETF），用于实盘"""
    sector_etf = _load_sector_etf_map()
    result = {}

    for sector, etf_codes in sector_etf.items():
        best = None
        for code in etf_codes:
            strength = _calc_etf_strength(code)
            if strength is not None:
                if best is None or strength['return'] > best['return']:
                    best = strength

        if best is None:
            result[sector] = {'level': 'weak', 'return': 0, 'vol_ratio': 1, 'bullish_align': False, 'is_main_rally': False}
            continue

        result[sector] = best

    # 找出市场最强板块（return最高的且is_main_rally的板块）
    rally_sectors = {s: v for s, v in result.items() if v.get('is_main_rally')}
    best_sector = max(rally_sectors, key=lambda s: rally_sectors[s]['return']) if rally_sectors else None

    for sector, info in result.items():
        is_best = (sector == best_sector)
        info['level'] = _classify_level(info, is_market_best=is_best)

    _print_sector_strength(result)
    return result


def get_sector_strength_at_date(etf_hist_map, date_str):
    """
    获取某一天的板块强度（用于回测，无前视偏差）
    """
    sector_etf = _load_sector_etf_map()
    result = {}

    for sector, etf_codes in sector_etf.items():
        best_strength = None
        for code in etf_codes:
            hist = etf_hist_map.get(code)
            if hist is None:
                continue
            dates = hist['日期'].astype(str)
            mask = dates <= date_str
            if mask.sum() < _STRENGTH_PERIOD:
                continue
            sub = hist[mask].copy()
            strength = _calc_etf_strength_from_hist(sub)
            if strength is not None:
                if best_strength is None or strength['return'] > best_strength['return']:
                    best_strength = strength

        result[sector] = _classify_level(best_strength)

    return result


def get_etf_sector(etf_code):
    """查询单只ETF所属板块"""
    df = _get_etf_df()
    row = df[df['代码'].astype(str).str.strip().str.zfill(6) == str(etf_code).zfill(6)]
    if len(row) > 0 and '所属板块' in df.columns:
        sector = str(row.iloc[0].get('所属板块', '')).strip()
        if sector:
            return sector
    return '其他'


def get_etf_main_rally_info(etf_code):
    """判断单只ETF是否属于主升板块，用于实盘ETF信号"""
    strength = _calc_etf_strength(etf_code)
    if strength is None:
        return False, '其他', 'weak'

    sector = get_etf_sector(etf_code)
    level = _classify_level(strength)
    return strength['is_main_rally'], sector, level


def load_etf_hist_map():
    """预加载所有行业板块ETF的历史数据，用于回测"""
    sector_etf = _load_sector_etf_map()
    all_codes = set()
    for codes in sector_etf.values():
        all_codes.update(codes)

    print(f"[INFO] 预加载 {len(all_codes)} 只行业板块ETF历史数据...")
    from market import prefetch_hist_batch
    prefetch_hist_batch(list(all_codes))

    etf_hist_map = {}
    for code in all_codes:
        hist = fetch_stock_hist(code, use_cache=True)
        if hist is not None and len(hist) >= 20:
            etf_hist_map[code] = hist

    print(f"[OK] 成功加载 {len(etf_hist_map)}/{len(all_codes)} 只行业板块ETF")
    return etf_hist_map


def _print_sector_strength(strength_map):
    """打印板块强度"""
    level_names = {'main': '主升', 'strong': '强势', 'main_fading': '主升尾声', 'rotating': '轮动', 'weak': '弱势'}
    print("\n[板块ETF强度]")
    sorted_sectors = sorted(strength_map.items(), key=lambda x: x[1].get('return', 0), reverse=True)
    for sector, info in sorted_sectors:
        level = info.get('level', 'weak')
        ret = info.get('return', 0)
        flag = ' <<<' if level in ('main', 'strong', 'main_fading') else ''
        print(f"  {sector}: {level_names[level]} {_STRENGTH_PERIOD}日{ret:.1%}{flag}")
