# backtest/report.py
import pandas as pd
import numpy as np


def generate_report(backtest_df, hold_days=10):
    """根据回测结果生成统计报告"""
    if backtest_df is None or backtest_df.empty:
        return {}

    ret_col = f'未来{hold_days}日收益'

    # 按得分区间统计
    bins = [(-999, -4), (-4, -1), (-1, 2), (2, 5), (5, 999)]
    labels = ['坚决卖出(≤-4)', '偏空(-3~-1)', '中性(-1~1)', '观望/试仓(2~4)', '强力买入(≥5)']

    backtest_df = backtest_df.copy()
    backtest_df['得分区间'] = pd.cut(
        backtest_df['得分'],
        bins=[b[0] for b in bins] + [bins[-1][1]],
        labels=labels,
        right=True,
        include_lowest=True,
    )

    stats = []
    for label in labels:
        group = backtest_df[backtest_df['得分区间'] == label]
        if len(group) == 0:
            stats.append({
                '得分区间': label, '样本数': 0,
                '胜率': '-', '平均收益': '-', '中位收益': '-',
                '最大收益': '-', '最大亏损': '-', '盈亏比': '-',
            })
            continue

        win_rate = group['是否盈利'].mean()
        avg_ret = group[ret_col].mean()
        med_ret = group[ret_col].median()
        max_ret = group[ret_col].max()
        min_ret = group[ret_col].min()

        # 盈亏比
        avg_win = group[group[ret_col] > 0][ret_col].mean() if (group[ret_col] > 0).any() else 0
        avg_loss = abs(group[group[ret_col] < 0][ret_col].mean()) if (group[ret_col] < 0).any() else 1
        pnl_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        stats.append({
            '得分区间': label,
            '样本数': len(group),
            '胜率': f'{win_rate:.1%}',
            '平均收益': f'{avg_ret:.2%}',
            '中位收益': f'{med_ret:.2%}',
            '最大收益': f'{max_ret:.2%}',
            '最大亏损': f'{min_ret:.2%}',
            '盈亏比': f'{pnl_ratio:.2f}',
        })

    # 按评级统计
    rating_stats = []
    for rating in ['强力买入', '观望/试仓', '中性', '坚决卖出']:
        group = backtest_df[backtest_df['评级'] == rating]
        if len(group) == 0:
            rating_stats.append({'评级': rating, '样本数': 0, '胜率': '-', '平均收益': '-', '盈亏比': '-'})
            continue

        avg_win = group[group[ret_col] > 0][ret_col].mean() if (group[ret_col] > 0).any() else 0
        avg_loss = abs(group[group[ret_col] < 0][ret_col].mean()) if (group[ret_col] < 0).any() else 1
        pnl_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        rating_stats.append({
            '评级': rating,
            '样本数': len(group),
            '胜率': f'{group["是否盈利"].mean():.1%}',
            '平均收益': f'{group[ret_col].mean():.2%}',
            '盈亏比': f'{pnl_ratio:.2f}',
        })

    # 高分段（≥5）细分
    high_score = backtest_df[backtest_df['得分'] >= 5]
    high_detail = None
    if len(high_score) >= 5:
        high_detail = {
            '强力买入样本数': len(high_score),
            '胜率': f'{high_score["是否盈利"].mean():.1%}',
            '平均收益': f'{high_score[ret_col].mean():.2%}',
            '得分5': _score_tier_stats(high_score, 5, 6, ret_col),
            '得分6': _score_tier_stats(high_score, 6, 7, ret_col),
            '得分7+': _score_tier_stats(high_score, 7, 999, ret_col),
        }

    # 全局核心指标
    returns = backtest_df[ret_col]
    win_mask = returns > 0
    overall_win_rate = win_mask.mean()
    avg_win = returns[win_mask].mean() if win_mask.any() else 0
    avg_loss = abs(returns[~win_mask].mean()) if (~win_mask).any() else 1
    overall_pnl_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    # 累计收益曲线 & 最大回撤
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    # 夏普比率（假设无风险利率3%/年，约244交易日）
    daily_rf = 0.03 / 244
    excess_returns = returns - daily_rf
    sharpe = np.sqrt(244) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0

    # 期望值
    expected_value = overall_win_rate * avg_win - (1 - overall_win_rate) * avg_loss

    core_metrics = {
        'total_samples': len(backtest_df),
        'date_range': f"{backtest_df['日期'].min()} ~ {backtest_df['日期'].max()}",
        'win_rate': overall_win_rate,
        'pnl_ratio': overall_pnl_ratio,
        'expected_value': expected_value,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'avg_return': returns.mean(),
        'median_return': returns.median(),
    }

    return {
        'core_metrics': core_metrics,
        'score_tier_stats': stats,
        'rating_stats': rating_stats,
        'high_score_detail': high_detail,
    }


def _score_tier_stats(df, low, high, ret_col):
    """细分得分统计"""
    group = df[(df['得分'] >= low) & (df['得分'] < high)]
    if len(group) == 0:
        return {'样本数': 0, '胜率': '-', '平均收益': '-'}
    return {
        '样本数': len(group),
        '胜率': f'{group["是否盈利"].mean():.1%}',
        '平均收益': f'{group[ret_col].mean():.2%}',
    }


def print_report(report):
    """打印格式化报告"""
    if not report:
        print("[WARN] 无回测数据")
        return

    m = report['core_metrics']

    print(f"\n{'='*60}")
    print(f"  策略回测报告")
    print(f"{'='*60}")

    # 核心指标
    print(f"\n--- 核心指标 ---")
    print(f"  总样本数: {m['total_samples']}")
    print(f"  时间范围: {m['date_range']}")
    print(f"  胜率:     {m['win_rate']:.1%}  (目标: 55%-60%)")
    print(f"  盈亏比:   {m['pnl_ratio']:.2f}:1  (目标: ≥2:1)")
    print(f"  期望值:   {m['expected_value']:.4f}  (正=长期盈利)")
    print(f"  最大回撤: {m['max_drawdown']:.1%}  (目标: ≤20%)")
    print(f"  夏普比率: {m['sharpe']:.2f}  (目标: ≥1.2)")
    print(f"  平均收益: {m['avg_return']:.2%}")
    print(f"  中位收益: {m['median_return']:.2%}")

    print(f"\n--- 按得分区间统计 ---")
    tier_df = pd.DataFrame(report['score_tier_stats'])
    print(tier_df.to_string(index=False))

    print(f"\n--- 按评级统计 ---")
    rating_df = pd.DataFrame(report['rating_stats'])
    print(rating_df.to_string(index=False))

    if report.get('high_score_detail'):
        detail = report['high_score_detail']
        print(f"\n--- 强力买入细分 ---")
        print(f"  总样本: {detail['强力买入样本数']}, 胜率: {detail['胜率']}, 平均收益: {detail['平均收益']}")
        for tier in ['得分5', '得分6', '得分7+']:
            d = detail[tier]
            print(f"  {tier}: 样本{d['样本数']}, 胜率{d['胜率']}, 平均收益{d['平均收益']}")

    print(f"{'='*60}")
