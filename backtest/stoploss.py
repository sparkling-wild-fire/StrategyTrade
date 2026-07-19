# factors/stoploss.py — 组合止损策略
# 规则：1. 亏损超-8%止损  2. 跌破MA10止损（取先触发的）

STOP_LOSS_PCT = -0.08  # 固定止损线 -8%
MA_PERIOD = 10          # 均线止损用MA10


def should_stop(buy_price, current_price, ma_value):
    """
    判断是否应该止损

    参数:
        buy_price: 买入价
        current_price: 当前价
        ma_value: 当前MA10值（None表示不判断均线止损）

    返回:
        (是否止损, 原因)
    """
    pnl = (current_price - buy_price) / buy_price

    # 1. 固定比例止损
    if pnl <= STOP_LOSS_PCT:
        return True, f'止损{pnl:.1%}(<{STOP_LOSS_PCT:.0%})'

    # 2. 均线止损：跌破MA10
    if ma_value is not None and current_price < ma_value:
        return True, f'跌破MA10(价{current_price:.2f}<MA{ma_value:.2f})'

    return False, ''
