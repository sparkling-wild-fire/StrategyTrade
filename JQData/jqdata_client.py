# JQData/jqdata_client.py
"""
聚宽JQData数据接口封装

优先使用JQData获取股票列表、历史行情、行业分类等数据，
akshare作为降级备用方案。
"""
import jqdatasdk as jq
from config import JQ_USERNAME, JQ_PASSWORD


def ensure_auth():
    """确保JQData已认证，未认证则自动登录"""
    if not jq.is_auth():
        jq.auth(JQ_USERNAME, JQ_PASSWORD)


def to_jqcode(symbol):
    """纯数字代码转聚宽格式（如 600048 → 600048.XSHG，000001 → 000001.XSHE）"""
    if '.' in symbol:
        return symbol
    suffix = '.XSHG' if symbol[:2] in ('60', '68') else '.XSHE'
    return f"{symbol}{suffix}"


def from_jqcode(jqcode):
    """聚宽格式代码转纯数字（如 600048.XSHG → 600048）"""
    return jqcode.split('.')[0]


# ==================== 股票列表 ====================

def get_stock_list(date=None):
    """
    获取全市场A股列表

    参数:
        date: str, 查询日期，默认使用账号有效期内的日期

    返回:
        DataFrame, 列: 代码(纯数字), 名称
    """
    ensure_auth()
    _date = date or _valid_date()

    stocks = jq.get_all_securities(types='stock', date=_date)
    # 筛选A股：60(沪市主板) 68(科创板) 00(深市主板) 30(创业板)
    prefixes = ('60', '68', '00', '30')
    stocks = stocks[stocks.index.str[:2].isin(prefixes)]

    result = stocks[['display_name']].copy()
    result.index = result.index.map(from_jqcode)
    result.index.name = '代码'
    result = result.rename(columns={'display_name': '名称'}).reset_index()
    return result


# ==================== 历史行情 ====================

def get_price(symbol, start_date=None, end_date=None, frequency='daily', fq='pre'):
    """
    获取单只股票历史行情数据

    参数:
        symbol: str, 纯数字股票代码（如 '600048'）
        start_date: str, 开始日期 'YYYY-MM-DD'
        end_date: str, 结束日期 'YYYY-MM-DD'
        frequency: str, 频率 'daily'/'minute'
        fq: str, 复权方式 'pre'(前复权)/'post'(后复权)/None(不复权)

    返回:
        DataFrame, 列: 日期, 开盘, 收盘, 最高, 最低, 成交量
        失败返回None
    """
    ensure_auth()

    jqcode = to_jqcode(symbol)
    try:
        df = jq.get_price(
            jqcode,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            fields=['open', 'close', 'high', 'low', 'volume'],
            skip_paused=True,
            fq=fq,
        )
    except Exception:
        return None

    if df is None or df.empty:
        return None

    df = df.reset_index()
    df = df.rename(columns={
        'index': '日期', 'date': '日期',
        'open': '开盘', 'close': '收盘',
        'high': '最高', 'low': '最低', 'volume': '成交量',
    })
    if '日期' not in df.columns:
        df = df.rename(columns={df.columns[0]: '日期'})
    df['日期'] = df['日期'].astype(str).str[:10]
    return df


# ==================== 行业分类 ====================

def get_industry(symbols, date=None):
    """
    批量获取股票行业分类

    参数:
        symbols: str 或 list, 纯数字股票代码或聚宽格式代码
        date: str, 查询日期

    返回:
        dict, {纯数字代码: {分类级别: {industry_code, industry_name}}}
    """
    ensure_auth()
    _date = date or _valid_date()

    if isinstance(symbols, str):
        symbols = [symbols]

    jqcodes = [to_jqcode(s) if '.' not in s else s for s in symbols]
    result = jq.get_industry(jqcodes, date=_date)

    # 将key转回纯数字代码
    normalized = {}
    for code, info in result.items():
        normalized[from_jqcode(code)] = info
    return normalized


def get_industries(name='sw_l1', date=None):
    """
    获取行业分类列表

    参数:
        name: str, 分类标准 'sw_l1'(申万一级)/'sw_l2'/'sw_l3'/'jq_l1'(聚宽一级)/'jq_l2'/'zjw'(证监会)
        date: str, 查询日期

    返回:
        DataFrame, 列: name(行业名), start_date
    """
    ensure_auth()
    _date = date or _valid_date()
    return jq.get_industries(name=name, date=_date)


# ==================== 概念板块 ====================

def get_concept(symbol, date=None):
    """
    获取股票所属概念板块

    参数:
        symbol: str, 纯数字或聚宽格式代码
        date: str, 查询日期

    返回:
        dict, {代码: {jq_concept: [{concept_code, concept_name}, ...]}}
    """
    ensure_auth()
    _date = date or _valid_date()
    jqcode = to_jqcode(symbol) if '.' not in symbol else symbol
    return jq.get_concept(jqcode, date=_date)


# ==================== 交易日 ====================

def get_trade_days(start_date=None, end_date=None):
    """
    获取交易日列表

    参数:
        start_date: str, 开始日期
        end_date: str, 结束日期

    返回:
        list, 交易日日期列表
    """
    ensure_auth()
    return jq.get_trade_days(start_date=start_date, end_date=end_date)


def get_prev_trade_date(ref_date=None):
    """
    获取指定日期的上一个交易日

    参数:
        ref_date: str, 参考日期，默认今天

    返回:
        str, 上一个交易日 'YYYY-MM-DD'
    """
    from datetime import datetime, timedelta
    ensure_auth()

    ref = ref_date or datetime.now().strftime('%Y-%m-%d')
    # 往前取10天确保覆盖假期
    start = (datetime.strptime(ref, '%Y-%m-%d') - timedelta(days=10)).strftime('%Y-%m-%d')
    days = jq.get_trade_days(start_date=start, end_date=ref)

    # 排除当天，取最后一个交易日
    if days and str(days[-1]) == ref:
        return str(days[-2]) if len(days) >= 2 else str(days[-1])
    return str(days[-1]) if days else ref


# ==================== ST状态 ====================

def get_is_st(symbols, date=None):
    """
    查询股票是否ST

    参数:
        symbols: list, 纯数字或聚宽格式代码列表
        date: str, 查询日期

    返回:
        dict, {纯数字代码: bool}
    """
    ensure_auth()
    _date = date or _valid_date()

    jqcodes = [to_jqcode(s) if '.' not in s else s for s in symbols]
    df = jq.get_extras('is_st', jqcodes, start_date=_date, end_date=_date)

    result = {}
    if df is not None and not df.empty:
        for col in df.columns:
            result[from_jqcode(col)] = bool(df[col].iloc[-1])
    return result


# ==================== 市值数据 ====================

def get_valuation(symbol, date=None, fields=None):
    """
    获取股票市值数据

    参数:
        symbol: str, 纯数字或聚宽格式代码
        date: str, 查询日期
        fields: list, 字段列表，默认全部。
            常用: code, day, market_cap(总市值), circulating_market_cap(流通市值),
            pe_ratio, pb_ratio, turnover_ratio

    返回:
        DataFrame
    """
    ensure_auth()
    _date = date or _valid_date()
    jqcode = to_jqcode(symbol) if '.' not in symbol else symbol
    return jq.get_valuation([jqcode], end_date=_date, count=1, fields=fields)


# ==================== 内部工具 ====================

def _valid_date():
    """动态获取账号有效期内的最新可用交易日"""
    from datetime import datetime
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        days = jq.get_trade_days(end_date=today, count=1)
        if days and len(days) > 0:
            return str(days[-1])[:10]
    except Exception as e:
        print(f"❌ JQData获取交易日失败: {e}")
    return None
