import pandas_ta_classic as ta  # noqa: F401 — 注册 .ta 访问器
from factors.macd import calculate as calc_macd, score as score_macd
from factors.kdj import calculate as calc_kdj, score as score_kdj
from factors.boll import calculate as calc_boll, score as score_boll
from factors.ma import calculate as calc_ma, score as score_trend
from factors.volume import calculate as calc_vol, score as score_volume
from factors.chase import score as score_chase
from factors.relative_strength import score as score_rs
from factors.sector_strength import score as score_sector_strength


def calculate_all(df):
    """计算所有因子，返回添加了指标列的DataFrame"""
    if len(df) < 35:
        return None

    df = df.copy()
    col_map = {'开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume'}
    df.rename(columns=col_map, inplace=True)

    calc_macd(df)
    calc_kdj(df)
    calc_boll(df)

    rev_map = {v: k for k, v in col_map.items()}
    df.rename(columns=rev_map, inplace=True)

    calc_ma(df)
    calc_vol(df)
    return df
