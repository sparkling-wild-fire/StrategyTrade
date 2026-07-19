# sector_etf.py — 用板块ETF判断当前主升板块
from market import fetch_stock_hist, get_etf_list
from sector import JQ_L1_TO_SECTOR

# 主升判定阈值
_MAIN_RALLY_RETURN = 0.06   # 20日涨幅>6%
_MAIN_RALLY_VOL_RATIO = 1.1  # 近5日均量 > 近20日均量*1.1

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
    if hist_df is None or len(hist_df) < 20:
        return None

    close = hist_df['收盘']
    volume = hist_df['成交量']

    ret_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
    vol_5 = volume.iloc[-5:].mean()
    vol_20 = volume.iloc[-20:].mean()
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1

    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    bullish_align = ma5 > ma10 > ma20

    is_main_rally = ret_20 > _MAIN_RALLY_RETURN and vol_ratio > _MAIN_RALLY_VOL_RATIO

    return {
        'return_20': ret_20,
        'vol_ratio': vol_ratio,
        'bullish_align': bullish_align,
        'is_main_rally': is_main_rally,
    }


def _classify_level(strength):
    """根据ETF强度信息分级"""
    if strength is None:
        return 'weak'
    if strength['is_main_rally']:
        return 'main'
    if strength['return_20'] > 0.02 and strength['bullish_align']:
        return 'rotating'
    if strength['return_20'] > 0:
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
                if best is None or strength['return_20'] > best['return_20']:
                    best = strength

        if best is None:
            result[sector] = {'level': 'weak', 'return_20': 0, 'vol_ratio': 1, 'bullish_align': False, 'is_main_rally': False}
            continue

        best['level'] = _classify_level(best)
        result[sector] = best

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
            if mask.sum() < 20:
                continue
            sub = hist[mask].copy()
            strength = _calc_etf_strength_from_hist(sub)
            if strength is not None:
                if best_strength is None or strength['return_20'] > best_strength['return_20']:
                    best_strength = strength

        result[sector] = _classify_level(best_strength)

    return result


def get_etf_sector(etf_code):
    """查询单只ETF所属板块"""
    df = _get_etf_df()
    row = df[df['代码'].astype(str).str.strip().str.zfill(6) == str(etf_code).zfill(6)]
    if len(row) > 0 and '所属板块' in df.columns:
        sector = str(row.iloc[0].get('所属板块', '')).strip()
        if sector and sector not in ('宽基', '红利', '策略', '区域', '央企'):
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
    level_names = {'main': '主升', 'rotating': '轮动', 'weak': '弱势'}
    print("\n[板块ETF强度]")
    sorted_sectors = sorted(strength_map.items(), key=lambda x: x[1].get('return_20', 0), reverse=True)
    for sector, info in sorted_sectors:
        level = info.get('level', 'weak')
        ret = info.get('return_20', 0)
        flag = ' <<<' if level == 'main' else ''
        print(f"  {sector}: {level_names[level]} 20日{ret:.1%}{flag}")
