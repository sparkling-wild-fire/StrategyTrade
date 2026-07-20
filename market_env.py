# market_env.py
import pandas as pd
from utils import retry_with_backoff

_INDEX_CONFIG = [
    ('sh000001', '上证指数', '000001'),
    ('sz399006', '创业板指', '399006'),
    ('sh000688', '科创50', '000688'),
    ('sh000852', '中证1000', '000852'),
]


def _fetch_index_hist(symbol='sh000001', days=120):
    """获取指数历史数据"""
    import akshare as ak
    df = ak.stock_zh_index_daily_tx(symbol=symbol)
    df = df.rename(columns={
        'date': '日期', 'open': '开盘', 'close': '收盘',
        'high': '最高', 'low': '最低', 'amount': '成交量',
    })
    df['日期'] = df['日期'].astype(str).str[:10]
    df = df.tail(days).reset_index(drop=True)
    return df


def _load_index_from_db(db_code, days=120):
    """从数据库读取指数历史数据"""
    from market.cache import _get_conn, _return_conn
    conn = _get_conn()
    try:
        sql = (
            "SELECT date AS 日期, open AS 开盘, close AS 收盘, "
            "high AS 最高, low AS 最低, volume AS 成交量 "
            "FROM trade_hishq WHERE code = %s ORDER BY date DESC LIMIT %s"
        )
        df = pd.read_sql_query(sql, conn, params=(db_code, days))
    finally:
        _return_conn(conn)
    if df.empty:
        return None
    df = df.iloc[::-1].reset_index(drop=True)  # 按日期正序
    return df


def _save_index_to_db(db_code, df):
    """将指数历史数据保存到数据库"""
    from market.cache import _get_conn, _return_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            rows = [
                (db_code, str(r['日期']), r['开盘'], r['收盘'], r['最高'], r['最低'], r['成交量'])
                for _, r in df.iterrows()
            ]
            cur.executemany(
                "REPLACE INTO trade_hishq (code, date, open, close, high, low, volume) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)", rows,
            )
        conn.commit()
    finally:
        _return_conn(conn)


def _get_index_hist(symbol, db_code, days=120):
    """获取指数历史数据：优先从DB读，缺失则走API并缓存"""
    df = _load_index_from_db(db_code, days)
    if df is not None and len(df) >= 60:
        return df

    df = retry_with_backoff(lambda: _fetch_index_hist(symbol, days))
    if df is not None and not df.empty:
        try:
            _save_index_to_db(db_code, df)
        except Exception:
            pass
    return df


def _analyze_index(symbol, db_code, days=120):
    """分析单个指数，返回分析结果或None"""
    try:
        df = _get_index_hist(symbol, db_code, days)
        if df is None or len(df) < 60:
            return None

        close = df['收盘'].astype(float)
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()

        curr_ma20 = ma20.iloc[-1]
        curr_ma60 = ma60.iloc[-1]
        ma20_above = curr_ma20 > curr_ma60

        golden = False
        death = False
        for i in range(-5, 0):
            if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
                golden = True
            if dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
                death = True

        # DIF持续在DEA下方（近5日DIF均<DEA）
        dif_below_dea = all(dif.iloc[i] < dea.iloc[i] for i in range(-5, 0))

        return {
            'ma20_above': ma20_above,
            'golden': golden,
            'death': death,
            'dif_below_dea': dif_below_dea,
            'ma20': curr_ma20,
            'ma60': curr_ma60,
        }
    except Exception:
        return None


def detect_market_env(enabled=True):
    """
    检测市场环境（牛市/震荡/熊市）

    多指数综合判断：
    - 熊市: 多数指数MA20<MA60（≥2/4），且(有死叉 或 DIF持续在DEA下方)
    - 牛市: 多数指数MA20>MA60（≥3/4），且至少一个近5日金叉
    - 震荡: 其他

    返回: 'bull' / 'bear' / 'range'
    """
    if not enabled:
        print("[INFO] 市场环境检测已禁用，默认震荡市")
        return 'range'

    results = {}
    for symbol, name, db_code in _INDEX_CONFIG:
        r = _analyze_index(symbol, db_code)
        if r is not None:
            results[name] = r

    if not results:
        print("[WARN] 指数数据全部获取失败，默认震荡市")
        return 'range'

    bear_count = sum(1 for r in results.values() if not r['ma20_above'])
    bull_count = sum(1 for r in results.values() if r['ma20_above'])
    has_death = any(r['death'] for r in results.values())
    has_dif_below = any(r['dif_below_dea'] for r in results.values())
    has_golden = any(r['golden'] for r in results.values())

    # 熊市：多数指数MA20<MA60，且MACD确认弱势
    if bear_count >= 2 and (has_death or has_dif_below):
        env = 'bear'
    # 牛市：多数指数MA20>MA60，且有金叉确认
    elif bull_count >= 3 and has_golden:
        env = 'bull'
    else:
        env = 'range'

    env_names = {'bull': '牛市/强势', 'bear': '熊市/弱势', 'range': '震荡市'}
    print(f"[OK] 市场环境: {env_names[env]}")
    for name, r in results.items():
        status = 'MA20>MA60' if r['ma20_above'] else 'MA20<MA60'
        cross = ''
        if r['golden']:
            cross = ' 金叉'
        if r['death']:
            cross = ' 死叉'
        if r['dif_below_dea'] and not r['death']:
            cross = ' DIF<DEA'
        print(f"       {name}: {status} (MA20={r['ma20']:.0f} MA60={r['ma60']:.0f}{cross})")

    return env
