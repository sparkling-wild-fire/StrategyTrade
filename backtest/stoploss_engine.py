# backtest/stoploss_engine.py — 带止损的回测引擎
import pandas as pd
from factors import calculate_all
from strategies import score_stock
from factors.stoploss import should_stop, MA_PERIOD


def run_stoploss_backtest(code, hist_df, buy_threshold=2, start_date=None, end_date=None,
                          min_hist=50, step=5, hold_days=20,
                          sector_map=None, etf_hist_map=None):
    """
    带止损的回测：买入后逐日检查止损条件

    规则:
    - 得分>=buy_threshold时买入
    - 买入后逐日检查：亏损超-8%或跌破MA10则止损卖出
    - 未触发止损则持有hold_days天后卖出
    - 计算实际收益（含止损）

    返回: DataFrame，每行一笔完整交易
    """
    if hist_df is None or len(hist_df) < min_hist + hold_days:
        return pd.DataFrame()

    hist_df = hist_df.copy()
    dates = hist_df['日期'].astype(str).tolist()
    n = len(dates)

    start_idx = min_hist
    end_idx = n - hold_days

    if start_date:
        candidates = [i for i in range(start_idx, end_idx) if dates[i] >= start_date]
        if candidates:
            start_idx = candidates[0]

    if end_date:
        candidates = [i for i in range(start_idx, end_idx) if dates[i] <= end_date]
        if candidates:
            end_idx = candidates[-1] + 1

    # 预计算MA10
    ma_col = f'MA{MA_PERIOD}'
    hist_df[ma_col] = hist_df['收盘'].rolling(MA_PERIOD).mean()

    results = []
    last_sell_idx = -1  # 上一次卖出的日期索引，避免重叠交易

    for i in range(start_idx, end_idx, step):
        if i <= last_sell_idx:
            continue  # 还在持仓中，跳过

        sub_df = hist_df.iloc[:i + 1].copy()
        df_ind = calculate_all(sub_df)
        if df_ind is None:
            continue

        result = score_stock(df_ind)
        if result is None:
            continue

        # 只在达到买入阈值时买入
        if result['total'] < buy_threshold:
            continue

        buy_price = float(hist_df['收盘'].iloc[i])
        buy_date = dates[i]
        buy_score = result['total']

        # 买入后逐日检查止损
        stop_triggered = False
        sell_idx = min(i + hold_days, n - 1)

        for j in range(i + 1, min(i + hold_days + 1, n)):
            current_price = float(hist_df['收盘'].iloc[j])
            ma_value = float(hist_df[ma_col].iloc[j]) if pd.notna(hist_df[ma_col].iloc[j]) else None

            is_stop, reason = should_stop(buy_price, current_price, ma_value)
            if is_stop:
                stop_triggered = True
                sell_idx = j
                break

        sell_price = float(hist_df['收盘'].iloc[sell_idx])
        actual_return = (sell_price - buy_price) / buy_price
        actual_hold = sell_idx - i

        results.append({
            '代码': code,
            '买入日期': buy_date,
            '卖出日期': dates[sell_idx],
            '买入价': round(buy_price, 2),
            '卖出价': round(sell_price, 2),
            '买入得分': buy_score,
            '实际持有天数': actual_hold,
            '实际收益': round(actual_return, 4),
            '是否盈利': actual_return > 0,
            '是否止损': stop_triggered,
            '止损原因': reason if stop_triggered else '',
            '板块类型': result.get('sector_type', ''),
        })

        last_sell_idx = sell_idx

    return pd.DataFrame(results)


def run_stoploss_batch(code_hist_map, buy_threshold=2, hold_days=20, step=5, min_hist=50):
    """批量止损回测"""
    all_results = []
    total = len(code_hist_map)
    done = 0

    for code, hist_df in code_hist_map.items():
        result_df = run_stoploss_backtest(
            code, hist_df, buy_threshold=buy_threshold, hold_days=hold_days,
            step=step, min_hist=min_hist,
        )
        done += 1
        if result_df is not None and not result_df.empty:
            all_results.append(result_df)
        if done % 20 == 0 or done == total:
            print(f"  回测进度 {done}/{total}")

    if all_results:
        return pd.concat(all_results, ignore_index=True)
    return pd.DataFrame()


def print_stoploss_report(df):
    """打印止损回测报告"""
    if df is None or df.empty:
        print("[WARN] 无回测数据")
        return

    total = len(df)
    win_rate = df['是否盈利'].mean()
    avg_ret = df['实际收益'].mean()
    med_ret = df['实际收益'].median()
    stop_count = df['是否止损'].sum()
    stop_pct = stop_count / total
    avg_hold = df['实际持有天数'].mean()

    # 非止损交易
    no_stop = df[~df['是否止损']]
    stop_df = df[df['是否止损']]

    print(f"\n{'='*60}")
    print(f"  止损回测报告")
    print(f"{'='*60}")
    print(f"  总交易数: {total}")
    print(f"  胜率: {win_rate:.1%}")
    print(f"  平均收益: {avg_ret:.2%}")
    print(f"  中位收益: {med_ret:.2%}")
    print(f"  平均持有: {avg_hold:.1f}天")
    print(f"  止损触发: {stop_count}次({stop_pct:.1%})")

    if len(no_stop) > 0:
        print(f"\n--- 正常卖出 ({len(no_stop)}笔) ---")
        print(f"  胜率: {no_stop['是否盈利'].mean():.1%}")
        print(f"  平均收益: {no_stop['实际收益'].mean():.2%}")
        print(f"  平均持有: {no_stop['实际持有天数'].mean():.1f}天")

    if len(stop_df) > 0:
        print(f"\n--- 止损卖出 ({len(stop_df)}笔) ---")
        print(f"  止损胜率(止损后盈利): {stop_df['是否盈利'].mean():.1%}")
        print(f"  止损平均收益: {stop_df['实际收益'].mean():.2%}")
        print(f"  止损平均持有: {stop_df['实际持有天数'].mean():.1f}天")

        # 止损原因统计
        print(f"\n  止损原因分布:")
        for reason_type in ['止损', '跌破MA10']:
            mask = stop_df['止损原因'].str.contains(reason_type, na=False)
            cnt = mask.sum()
            if cnt > 0:
                avg = stop_df[mask]['实际收益'].mean()
                print(f"    {reason_type}: {cnt}次 平均收益{avg:.2%}")

    # 按买入得分区间统计
    print(f"\n--- 按买入得分统计 ---")
    for lo, hi, label in [(2, 4, '观望(2~4)'), (5, 7, '强力(5~6)'), (7, 999, '极强(7+)')]:
        group = df[(df['买入得分'] >= lo) & (df['买入得分'] < hi)]
        if len(group) > 0:
            print(f"  {label}: {len(group)}笔  胜率{group['是否盈利'].mean():.1%}  "
                  f"平均收益{group['实际收益'].mean():.2%}  "
                  f"止损率{group['是否止损'].mean():.1%}")

    print(f"{'='*60}")
