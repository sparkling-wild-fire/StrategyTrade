# main.py
import os
os.environ['TQDM_DISABLE'] = '1'

import csv
import time
import threading
import traceback
import datetime
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from market import get_stock_list, fetch_stock_hist, prefetch_hist_batch, fetch_spot_data, filter_a_stocks, get_etf_list
from factors import calculate_all
from strategies import score_stock
from sector import get_sector_map, classify
from sector_etf import get_sector_strength, get_etf_main_rally_info, get_etf_sector
from fundamental_filter import filter_by_fundamentals
from market_env import detect_market_env
from feishu.notify import send_interactive
from config import FUNDAMENTAL_FILTER_ENABLED, MARKET_ENV_ENABLED, BEAR_BUY_THRESHOLD, FEISHU_WEBHOOK_URL

MAX_WORKERS = 5
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
BUY_CSV = os.path.join(OUTPUT_DIR, 'buy_signals.csv')
BUY_ETF_CSV = os.path.join(OUTPUT_DIR, 'buy_etf_signals.csv')
SALE_CSV = os.path.join(OUTPUT_DIR, 'sale_signals.csv')
BUY_THRESHOLD = 2
SALE_THRESHOLD = -2

_CSV_FIELDS = ['代码', '名称', '板块', '日期', '收盘价', '综合得分', 'MACD得分', 'KDJ得分', 'BB得分', '量价得分', '追涨得分', '趋势得分', '相对强度得分', '板块类型', '是否主升', '评级', '建议仓位', '建议持有', '明细']

from config import ETF_PREFIXES


def _is_etf_code(code):
    return str(code)[:2] in ETF_PREFIXES


def _hold_suggestion(level):
    if level == 'main':
        return '1~2月'
    elif level == 'rotating':
        return '2~4周'
    else:
        return '1~2周'


def _position_map(level, total):
    if level == 'main':
        if total >= 5:
            return '60%'
        elif total >= 2:
            return '30%'
    else:
        if total >= 5:
            return '50%'
        elif total >= 2:
            return '20%'
    return '0%'

_lock = threading.Lock()
_done = 0
_buy_results = []
_sale_results = []
_buy_csv_written = False
_buy_etf_csv_written = False
_sale_csv_written = False
_sector_map = {}
_market_env = 'range'


def _append_csv(path, row, written_flag_name):
    """追加一行到CSV文件"""
    global _buy_csv_written, _buy_etf_csv_written, _sale_csv_written
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if written_flag_name == 'buy':
        written = _buy_csv_written
    elif written_flag_name == 'buy_etf':
        written = _buy_etf_csv_written
    else:
        written = _sale_csv_written
    with _lock:
        write_header = not written
        if write_header:
            if written_flag_name == 'buy':
                _buy_csv_written = True
            elif written_flag_name == 'buy_etf':
                _buy_etf_csv_written = True
            else:
                _sale_csv_written = True
    with open(path, 'a', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=',')
        if write_header:
            writer.writerow(_CSV_FIELDS)
        writer.writerow([str(row.get(k, '')) for k in _CSV_FIELDS])


def _compute_sector_info(df_with_indicators_list, sector_map):
    """预计算各板块20日平均涨幅、上涨占比、成交量趋势"""
    sector_data = {}
    for code, df in df_with_indicators_list:
        if df is None or len(df) < 20:
            continue
        sector = classify(code, sector_map)
        try:
            close = df['收盘']
            volume = df['成交量']
            ret = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
            is_up = close.iloc[-1] > close.iloc[-20]
            vol_5 = volume.iloc[-5:].mean()
            vol_20 = volume.iloc[-20:].mean()
            vol_trend = 1 if vol_5 > vol_20 * 1.2 else (-1 if vol_5 < vol_20 * 0.8 else 0)
            sector_data.setdefault(sector, {'returns': [], 'up_count': 0, 'total_count': 0, 'vol_trends': []})
            sector_data[sector]['returns'].append(ret)
            sector_data[sector]['total_count'] += 1
            if is_up:
                sector_data[sector]['up_count'] += 1
            sector_data[sector]['vol_trends'].append(vol_trend)
        except Exception:
            pass

    sector_info = {}
    for sector, data in sector_data.items():
        returns = data['returns']
        avg_ret = sum(returns) / len(returns) if returns else 0
        up_ratio = data['up_count'] / data['total_count'] if data['total_count'] > 0 else 0.5
        vol_trend = 0
        if data['vol_trends']:
            vol_trend = round(sum(data['vol_trends']) / len(data['vol_trends']))
        sector_info[sector] = {
            'avg_return': avg_ret,
            'up_ratio': up_ratio,
            'vol_trend': vol_trend,
        }
    return sector_info


def analyze_one(code, name, spot_data=None, sector_avg_return=None, sector_up_ratio=None, sector_vol_trend=None, sector_level=None):
    """分析单只股票/ETF，返回评分结果或None"""
    try:
        hist_df = fetch_stock_hist(code)
        if hist_df is None or hist_df.empty:
            return None

        if spot_data and code in spot_data:
            today_bar = spot_data[code]
            today = today_bar['日期']
            if str(hist_df['日期'].iloc[-1]) < today:
                hist_df = pd.concat([hist_df, pd.DataFrame([today_bar])], ignore_index=True)

        df_with_indicators = calculate_all(hist_df)
        if df_with_indicators is None:
            return None

        result = score_stock(
            df_with_indicators,
            sector_avg_return=sector_avg_return,
            sector_up_ratio=sector_up_ratio,
            sector_vol_trend=sector_vol_trend,
            sector_level=sector_level,
        )
        if result is None:
            return None

        curr = df_with_indicators.iloc[-1]
        result['代码'] = code
        result['名称'] = name
        result['日期'] = curr['日期']
        result['收盘价'] = curr['收盘']

        # ETF用etf_info的板块，股票用聚宽行业分类
        if _is_etf_code(code):
            etf_sector = get_etf_sector(code)
            result['板块'] = etf_sector
            # ETF用自身趋势强度判断板块类型
            is_main, _, level = get_etf_main_rally_info(code)
            if level and sector_level is None:
                result['sector_type'] = level
                result['hold_suggestion'] = _hold_suggestion(level)
                result['position'] = _position_map(level, result['total'])
                if is_main:
                    result['details'].append('🔥ETF主升')
        else:
            result['板块'] = classify(code, _sector_map)

        return result
    except Exception:
        pass
    return None


def _run_batch(code_name_list, label, check_sale=False, spot_data=None, buy_threshold=BUY_THRESHOLD):
    """批量分析并输出结果"""
    global _done
    total = len(code_name_list)
    buy_count = 0
    sale_count = 0

    # 预加载历史数据并计算指标，用于板块平均涨幅
    hist_cache = {}
    for code, name in code_name_list:
        try:
            hist_df = fetch_stock_hist(code)
            if hist_df is not None and not hist_df.empty:
                if spot_data and code in spot_data:
                    today_bar = spot_data[code]
                    today = today_bar['日期']
                    if str(hist_df['日期'].iloc[-1]) < today:
                        hist_df = pd.concat([hist_df, pd.DataFrame([today_bar])], ignore_index=True)
                df_ind = calculate_all(hist_df)
                if df_ind is not None:
                    hist_cache[code] = df_ind
        except Exception:
            pass

    sector_avg = _compute_sector_info(list(hist_cache.items()), _sector_map)

    # 用板块ETF判断当前主升板块
    etf_sector_strength = get_sector_strength()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for code, name in code_name_list:
            sector = classify(code, _sector_map)
            info = sector_avg.get(sector, {})
            # 优先用ETF板块强度
            etf_info = etf_sector_strength.get(sector, {})
            sector_level = etf_info.get('level')
            f = pool.submit(analyze_one, code, name, spot_data,
                            info.get('avg_return'), info.get('up_ratio'), info.get('vol_trend'),
                            sector_level)
            futures[f] = (code, name)

        for f in as_completed(futures):
            code, name = futures[f]

            with _lock:
                _done += 1
                done = _done

            result = f.result()

            with _lock:
                buy_found = len(_buy_results)
                sale_found = len(_sale_results)

            if result is None:
                print(f"\r  [{label} {done}/{total}] 买入{buy_found} 危出{sale_found}          ", end='', flush=True)
                continue

            row_data = {
                '代码': result['代码'], '名称': result['名称'],
                '板块': result['板块'],
                '日期': result['日期'], '收盘价': result['收盘价'],
                '综合得分': result['total'],
                'MACD得分': result['macd_score'],
                'KDJ得分': result['kdj_score'],
                'BB得分': result['bb_score'],
                '量价得分': result['vol_score'],
                '追涨得分': result['chase_score'],
                '趋势得分': result['trend_score'],
                '相对强度得分': result.get('rs_score', 0),
                '板块类型': result.get('sector_type', ''),
                '是否主升': '是' if result.get('sector_type') == 'main' else '',
                '评级': result['rating'],
                '建议仓位': result.get('position', '0%'),
                '建议持有': result.get('hold_suggestion', ''),
                '明细': '; '.join(result['details']),
            }

            is_buy = result['total'] >= buy_threshold
            is_sale = check_sale and result['total'] <= SALE_THRESHOLD

            if is_buy:
                with _lock:
                    _buy_results.append(result)
                    buy_found = len(_buy_results)
                    buy_count += 1
                csv_flag = 'buy_etf' if label == 'ETF' else 'buy'
                csv_path = BUY_ETF_CSV if label == 'ETF' else BUY_CSV
                _append_csv(csv_path, row_data, csv_flag)

            if is_sale:
                with _lock:
                    _sale_results.append(result)
                    sale_found = len(_sale_results)
                    sale_count += 1
                _append_csv(SALE_CSV, row_data, 'sale')

            with _lock:
                buy_found = len(_buy_results)
                sale_found = len(_sale_results)

            if is_buy:
                print(f"  [BUY] [{label} {done}/{total}] {code} {name} [{result['板块']}] 得分{result['total']} {result['rating']} 仓位{result.get('position','0%')} | 买入{buy_found}只")
            elif is_sale:
                print(f"  [SALE] [{label} {done}/{total}] {code} {name} [{result['板块']}] 得分{result['total']} {result['rating']} | 危出{sale_found}只")
            else:
                print(f"\r  [{label} {done}/{total}] 买入{buy_found} 危出{sale_found}          ", end='', flush=True)

    return buy_count, sale_count


def calculate_buy_signals(stock_list, etf_list, spot_data=None, buy_threshold=BUY_THRESHOLD):
    """计算买入信号：对股票和ETF分别批量分析"""
    total = len(stock_list) + len(etf_list)
    print(f"\n[INFO] 开始买入信号分析 {total} 只（证券{len(stock_list)} + ETF{len(etf_list)}）"
          f"（{MAX_WORKERS}线程并发，买入阈值≥{buy_threshold}）...\n")

    _run_batch(stock_list, '证券', check_sale=False, spot_data=spot_data, buy_threshold=buy_threshold)
    _run_batch(etf_list, 'ETF', check_sale=False, spot_data=spot_data, buy_threshold=buy_threshold)


def calculate_sell_signals(sale_codes, all_codes, spot_data=None):
    """计算卖出信号：仅分析指定证券代码"""
    if not sale_codes:
        return

    sale_list = []
    for code in sale_codes:
        code = str(code).strip()
        name = all_codes.get(code, code)
        sale_list.append((code, name))

    print(f"\n[INFO] 开始卖出信号分析 {len(sale_list)} 只指定证券/ETF...\n")
    prefetch_hist_batch([c for c, _ in sale_list])
    _run_batch(sale_list, '卖出', check_sale=True, spot_data=spot_data)


def main(sale_codes=None, max_count=0):
    """
    主入口函数

    参数:
        sale_codes: 需要计算卖出信号的证券代码列表，默认为空不计算
        max_count: 最多分析的证券数量，0表示全部（用于调试验证）
    """
    global _done, _buy_results, _sale_results, _buy_csv_written, _sale_csv_written, _sector_map, _market_env
    _done = 0
    _buy_results = []
    _sale_results = []
    _buy_csv_written = False
    _buy_etf_csv_written = False
    _sale_csv_written = False

    if sale_codes is None:
        from config import SALE_CODES
        sale_codes = SALE_CODES

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for p in (BUY_CSV, BUY_ETF_CSV, SALE_CSV):
        if os.path.exists(p):
            os.remove(p)

    _start = time.time()

    # ======== 获取数据 ========

    print("[INFO] 开始获取并筛选股票列表...")
    raw_df = get_stock_list()
    stock_df = filter_a_stocks(raw_df)

    etf_df = get_etf_list()

    _sector_map = get_sector_map()

    all_codes = {}
    for _, row in stock_df.iterrows():
        all_codes[str(row['代码']).zfill(6)] = row['名称']
    for _, row in etf_df.iterrows():
        all_codes[str(row['代码']).zfill(6)] = row['名称']

    # ======== 基本面前置过滤 ========

    stock_list = [(str(row['代码']).zfill(6), row['名称']) for _, row in stock_df.iterrows()]
    etf_list = [(str(row['代码']).zfill(6), row['名称']) for _, row in etf_df.iterrows()]

    stock_list, excluded = filter_by_fundamentals(stock_list, enabled=FUNDAMENTAL_FILTER_ENABLED)

    # ======== 市场环境检测 ========

    _market_env = detect_market_env(enabled=MARKET_ENV_ENABLED)
    if _market_env == 'bear':
        effective_buy_threshold = BEAR_BUY_THRESHOLD
        print(f"[INFO] 熊市环境，买入阈值提高到 ≥{effective_buy_threshold}")
    else:
        effective_buy_threshold = BUY_THRESHOLD

    # ======== 批量预加载 ========

    if max_count > 0:
        stock_list = stock_list[:max_count]
        etf_list = etf_list[:max_count]
        print(f"[WARN] 调试模式：仅分析前 {max_count} 只证券 + 前 {max_count} 只ETF")

    analyze_codes = [c for c, _ in stock_list] + [c for c, _ in etf_list]
    if sale_codes:
        analyze_codes += [str(c).strip() for c in sale_codes]
    prefetch_hist_batch(analyze_codes)

    spot_data = fetch_spot_data()

    # ======== 买入信号：证券+ETF ========

    calculate_buy_signals(stock_list, etf_list, spot_data=spot_data, buy_threshold=effective_buy_threshold)

    # ======== 卖出信号：仅分析指定代码 ========

    calculate_sell_signals(sale_codes, all_codes, spot_data=spot_data)

    # ======== 结果汇总 ========

    with _lock:
        buy_found = len(_buy_results)
        sale_found = len(_sale_results)

    elapsed = time.time() - _start
    print(f"\n\n[OK] 分析完成！")
    print(f"  买入信号: {buy_found}只 (得分>={effective_buy_threshold})")
    if sale_codes:
        print(f"  危出信号: {sale_found}只 (得分<={SALE_THRESHOLD})")
    else:
        print(f"  危出信号: 未计算 (sale_codes为空)")
    print(f"  耗时 {elapsed:.1f}s")
    print(f"  买入信号(股票) -> {BUY_CSV}")
    print(f"  买入信号(ETF)  -> {BUY_ETF_CSV}")
    if sale_codes:
        print(f"  危出信号 -> {SALE_CSV}")

    if _buy_results:
        print("\n[买入信号TOP]:")
        buy_out = pd.DataFrame([{
            '代码': r['代码'], '名称': r['名称'],
            '板块': r['板块'],
            '收盘价': r['收盘价'], '综合得分': r['total'],
            'MACD': r['macd_score'], 'KDJ': r['kdj_score'], 'BB': r['bb_score'],
            '量价': r['vol_score'], '追涨': r['chase_score'],
            'RS': r.get('rs_score', 0), '仓位': r.get('position', '0%'),
            '评级': r['rating'], '明细': '; '.join(r['details']),
        } for r in sorted(_buy_results, key=lambda x: x['total'], reverse=True)])
        print(buy_out.to_string(index=False))

    if _sale_results:
        print("\n[危出信号TOP]:")
        sale_out = pd.DataFrame([{
            '代码': r['代码'], '名称': r['名称'],
            '板块': r['板块'],
            '收盘价': r['收盘价'], '综合得分': r['total'],
            'MACD': r['macd_score'], 'KDJ': r['kdj_score'], 'BB': r['bb_score'],
            '量价': r['vol_score'], '追涨': r['chase_score'],
            'RS': r.get('rs_score', 0), '仓位': r.get('position', '0%'),
            '评级': r['rating'], '明细': '; '.join(r['details']),
        } for r in sorted(_sale_results, key=lambda x: x['total'])])
        print(sale_out.to_string(index=False))

    _notify_success(buy_found, sale_found, elapsed, sale_codes, effective_buy_threshold)


def _notify_success(buy_found, sale_found, elapsed, sale_codes, buy_threshold):
    """运行成功通知"""
    if not FEISHU_WEBHOOK_URL:
        return

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    env_names = {'bull': '牛市', 'bear': '熊市', 'range': '震荡'}
    content = f"**时间**: {now}\n**耗时**: {elapsed:.1f}s\n**市场环境**: {env_names.get(_market_env, _market_env)}\n\n"
    content += f"**买入信号**: {buy_found}只 (得分>={buy_threshold})\n"
    if sale_codes:
        content += f"**卖出信号**: {sale_found}只 (得分<={SALE_THRESHOLD})\n"
    else:
        content += "**卖出信号**: 未计算\n"
    content += f"\n**结果文件**: `{BUY_CSV}`"

    if _buy_results:
        top5 = sorted(_buy_results, key=lambda x: x['total'], reverse=True)[:5]
        content += "\n\n**买入TOP5**:\n"
        for i, r in enumerate(top5, 1):
            content += f"{i}. {r['代码']} {r['名称']} [{r['板块']}] 得分{r['total']} {r['rating']} 仓位{r.get('position','0%')}\n"

    send_interactive(FEISHU_WEBHOOK_URL, "交易分析完成", content)


def _notify_failure(error_msg):
    """运行失败通知"""
    if not FEISHU_WEBHOOK_URL:
        return

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"**时间**: {now}\n**状态**: 运行失败\n\n**错误**:\n```\n{error_msg}\n```"
    send_interactive(FEISHU_WEBHOOK_URL, "交易分析失败", content)


if __name__ == "__main__":
    from config import SALE_CODES
    try:
        main(sale_codes=SALE_CODES)
    except Exception:
        _notify_failure(traceback.format_exc())
        raise
