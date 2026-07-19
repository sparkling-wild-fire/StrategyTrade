# sector.py
import os
import json
import time
from JQData import ensure_auth, get_industry, from_jqcode
from config import JQ_USERNAME, JQ_PASSWORD

_CACHE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'sector_cache.json')
_CACHE_TTL = 7 * 86400  # 7天过期

# 聚宽一级行业 → 用户友好大类板块（与ETF板块分类对齐）
JQ_L1_TO_SECTOR = {
    '房地产': '房产',
    '主要消费': '消费',
    '可选消费': '消费',
    '信息技术': '科技',
    '通信服务': '科技',
    '医药卫生': '医药',
    '金融': '金融',
    '工业': '制造',
    '原材料': '周期',
    '能源': '周期',
    '公用事业': '新能源',
}


def _fetch_sector_mapping():
    """从聚宽JQData批量获取行业分类，返回 {code: jq_l1_name}"""
    print("[INFO] 从JQData拉取行业分类...")
    ensure_auth()

    import jqdatasdk as jq
    _date = '2026-04-10'

    # 获取全市场股票
    stocks = jq.get_all_securities(types='stock', date=_date)
    prefixes = ('60', '68', '00', '30')
    codes = stocks[stocks.index.str[:2].isin(prefixes)].index.tolist()

    # 批量获取行业
    result = jq.get_industry(codes, date=_date)

    code_to_industry = {}
    for code, info in result.items():
        jq_l1 = info.get('jq_l1', {})
        industry_name = jq_l1.get('industry_name', '')
        pure_code = from_jqcode(code)
        code_to_industry[pure_code] = industry_name

    print(f"[OK] 行业分类获取完成，共 {len(code_to_industry)} 只股票")
    return code_to_industry


def _load_cache():
    """从JSON缓存加载板块映射，过期返回None"""
    if not os.path.exists(_CACHE_PATH):
        return None
    try:
        with open(_CACHE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        updated = data.get('updated', 0)
        if time.time() - updated > _CACHE_TTL:
            return None
        return data.get('mapping', {})
    except Exception:
        return None


def _save_cache(mapping):
    """保存板块映射到JSON缓存"""
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    data = {
        'updated': time.time(),
        'mapping': mapping,
    }
    with open(_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def get_sector_map():
    """获取 code→jq_l1行业名 映射（缓存优先）"""
    mapping = _load_cache()
    if mapping is not None:
        print(f"[OK] 板块缓存有效，共 {len(mapping)} 只股票")
        return mapping

    mapping = _fetch_sector_mapping()
    if mapping:
        _save_cache(mapping)
    return mapping


def classify(code, sector_map):
    """根据股票代码返回大类板块名，未分类返回'其他'"""
    industry = sector_map.get(str(code), '')
    if not industry:
        return '其他'
    return JQ_L1_TO_SECTOR.get(industry, '其他')
