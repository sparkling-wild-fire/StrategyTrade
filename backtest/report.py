# backtest/report.py
import pandas as pd


def generate_report(backtest_df, hold_days=10):
    """
    根据回测结果生成统计报告

    参数:
        backtest_df: run_single或run_batch返回的DataFrame
        hold_days: 持有天数

    返回:
        dict，包含按得分区间的胜率、平均收益等统计
    """
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
                '得分区间': label,
                '样本数': 0,
                '胜率': '-',
                '平均收益': '-',
                '中位收益': '-',
                '最大收益': '-',
                '最大亏损': '-',
            })
            continue

        win_rate = group['是否盈利'].mean()
        avg_ret = group[ret_col].mean()
        med_ret = group[ret_col].median()
        max_ret = group[ret_col].max()
        min_ret = group[ret_col].min()

        stats.append({
            '得分区间': label,
            '样本数': len(group),
            '胜率': f'{win_rate:.1%}',
            '平均收益': f'{avg_ret:.2%}',
            '中位收益': f'{med_ret:.2%}',
            '最大收益': f'{max_ret:.2%}',
            '最大亏损': f'{min_ret:.2%}',
        })

    # 按评级统计
    rating_stats = []
    for rating in ['强力买入', '观望/试仓', '中性', '坚决卖出']:
        group = backtest_df[backtest_df['评级'] == rating]
        if len(group) == 0:
            rating_stats.append({
                '评级': rating,
                '样本数': 0,
                '胜率': '-',
                '平均收益': '-',
            })
            continue

        rating_stats.append({
            '评级': rating,
            '样本数': len(group),
            '胜率': f'{group["是否盈利"].mean():.1%}',
            '平均收益': f'{group[ret_col].mean():.2%}',
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

    return {
        'total_samples': len(backtest_df),
        'date_range': f"{backtest_df['日期'].min()} ~ {backtest_df['日期'].max()}",
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

    print(f"\n{'='*60}")
    print(f"  策略回测报告")
    print(f"{'='*60}")
    print(f"  总样本数: {report['total_samples']}")
    print(f"  时间范围: {report['date_range']}")

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
