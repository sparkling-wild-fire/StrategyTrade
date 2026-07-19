# market_env.py
import pandas as pd
from utils import retry_with_backoff


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


def detect_market_env(enabled=True):
    """
    检测市场环境（牛市/震荡/熊市）

    判断逻辑:
    - 牛市: 上证MA20 > MA60 且 MACD金叉(近5日DIF上穿DEA)
    - 熊市: 上证MA20 < MA60 且 MACD死叉(近5日DIF下穿DEA)
    - 震荡: 其他

    返回: 'bull' / 'bear' / 'range'
    """
    if not enabled:
        print("[INFO] 市场环境检测已禁用，默认震荡市")
        return 'range'

    try:
        df = retry_with_backoff(_fetch_index_hist)
        if df is None or len(df) < 60:
            print("[WARN] 指数数据不足，默认震荡市")
            return 'range'

        close = df['收盘'].astype(float)
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()

        curr_ma20 = ma20.iloc[-1]
        curr_ma60 = ma60.iloc[-1]

        # 检查近5日金叉/死叉
        golden = False
        death = False
        for i in range(-5, 0):
            if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
                golden = True
            if dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
                death = True

        if curr_ma20 > curr_ma60 and golden:
            env = 'bull'
        elif curr_ma20 < curr_ma60 and death:
            env = 'bear'
        else:
            env = 'range'

        env_names = {'bull': '牛市/强势', 'bear': '熊市/弱势', 'range': '震荡市'}
        print(f"[OK] 市场环境: {env_names[env]} (MA20={curr_ma20:.0f} MA60={curr_ma60:.0f} 金叉={golden} 死叉={death})")
        return env

    except Exception as e:
        print(f"[WARN] 市场环境检测失败: {e}，默认震荡市")
        return 'range'
