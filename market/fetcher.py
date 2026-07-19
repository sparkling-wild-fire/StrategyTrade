import os
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import retry_with_backoff
from market.cache import get_last_date, get_last_check, set_last_check, save_hist, load_hist, get_cached_codes, get_stale_codes
from config import ETF_PREFIXES

_CACHE_FILE = os.path.join(os.path.dirname(__file__), '.last_source')

# 英文列名 -> 中文列名映射
_COL_RENAME = {
    'date': '日期', 'time': '日期',
    'open': '开盘', 'high': '最高', 'low': '最低',
    'close': '收盘', 'volume': '成交量',
}
# 腾讯特有：amount实际是成交量（手）
_TX_RENAME = {
    'date': '日期', 'open': '开盘', 'close': '收盘',
    'high': '最高', 'low': '最低', 'amount': '成交量',
}
# 最终只保留这6列
_KEEP_COLS = ['日期', '开盘', '收盘', '最高', '最低', '成交量']


def _prev_trade_date():
    """获取上一个交易日（简单跳过周末）"""
    d = datetime.now() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def _normalize_code(df):
    """统一代码格式：去掉市场前缀(sh/sz/bj)，保留纯数字"""
    df['代码'] = df['代码'].str.replace(r'^(sh|sz|bj)', '', regex=True)
    return df


def _is_etf(symbol):
    return symbol[:2] in ETF_PREFIXES


def _market_prefix(symbol):
    """返回市场前缀 sh/sz"""
    return 'sh' if symbol[:2] in ('60', '68', '51', '52', '53', '56', '58') else 'sz'


def _normalize_hist_columns(df, col_map=None):
    """统一历史数据列名为中文格式，只保留需要的列"""
    if df is None or df.empty:
        return df
    rename = {k: v for k, v in (col_map or _COL_RENAME).items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)
    if '日期' in df.columns:
        df['日期'] = df['日期'].astype(str).str[:10]
    keep = [c for c in _KEEP_COLS if c in df.columns]
    return df[keep]


# ==================== 股票列表 ====================

def fetch_stock_list_sina():
    """从新浪财经获取A股列表"""
    df = ak.stock_zh_a_spot()
    return _normalize_code(df)


def get_stock_list():
    """获取A股列表，使用新浪财经"""
    try:
        print("[INFO] 从新浪财经获取股票列表...")
        df = retry_with_backoff(fetch_stock_list_sina)
        print(f"[OK] 成功获取 {len(df)} 只股票")
        return df
    except Exception as e:
        print(f"[ERR] 新浪财经获取失败: {e}")
        raise


# ==================== 盘中实时行情 ====================

def fetch_spot_data():
    """获取全市场盘中实时行情，返回 {code: {日期,开盘,收盘,最高,最低,成交量}}"""
    today = datetime.now().strftime('%Y-%m-%d')
    spot = {}

    # 股票：新浪财经
    try:
        print("[INFO] 获取股票盘中行情...")
        df = ak.stock_zh_a_spot()
        df = _normalize_code(df)
        for _, r in df.iterrows():
            try:
                code = str(r['代码'])
                spot[code] = {
                    '日期': today,
                    '开盘': float(r['今开']),
                    '收盘': float(r['最新价']),
                    '最高': float(r['最高']),
                    '最低': float(r['最低']),
                    '成交量': float(r['成交量']),
                }
            except (ValueError, TypeError, KeyError):
                continue
        print(f"[OK] 股票盘中行情 {len(spot)} 只")
    except Exception as e:
        print(f"[ERR] 获取股票盘中行情失败: {e}")

    # ETF：东方财富（单次请求不封IP）
    try:
        print("[INFO] 获取ETF盘中行情...")
        df = ak.fund_etf_spot_em()
        for _, r in df.iterrows():
            try:
                code = str(r['代码'])
                spot[code] = {
                    '日期': today,
                    '开盘': float(r['开盘价']),
                    '收盘': float(r['最新价']),
                    '最高': float(r['最高价']),
                    '最低': float(r['最低价']),
                    '成交量': float(r['成交量']),
                }
            except (ValueError, TypeError, KeyError):
                continue
        print(f"[OK] ETF盘中行情追加 {len(df)} 只")
    except Exception as e:
        print(f"[ERR] 获取ETF盘中行情失败: {e}")

    return spot

def _fetch_hist(symbol, start_date=None, end_date=None):
    """
    获取历史数据：股票用腾讯，ETF用新浪财经
    返回统一中文列名
    """
    start = (start_date or (datetime.now() - timedelta(days=3650)).strftime('%Y%m%d')).replace('-', '')
    end = (end_date or datetime.now().strftime('%Y%m%d')).replace('-', '')

    if _is_etf(symbol):
        # ETF: 新浪财经（只接受symbol，返回全量历史，需按日期过滤）
        prefix = _market_prefix(symbol)
        df = ak.fund_etf_hist_sina(symbol=f'{prefix}{symbol}')
        df = _normalize_hist_columns(df, _COL_RENAME)
        if '日期' in df.columns:
            start_fmt = start[:4] + '-' + start[4:6] + '-' + start[6:8]
            end_fmt = end[:4] + '-' + end[4:6] + '-' + end[6:8]
            df = df[(df['日期'] >= start_fmt) & (df['日期'] <= end_fmt)]
    else:
        # 股票: 腾讯（amount=成交量手）
        prefix = _market_prefix(symbol)
        df = ak.stock_zh_a_hist_tx(symbol=f'{prefix}{symbol}', start_date=start, end_date=end, adjust='qfq')
        df = _normalize_hist_columns(df, _TX_RENAME)

    return df


# ==================== 带缓存的历史数据获取 ====================

def _fetch_from_api(symbol, start_date=None, end_date=None):
    """拉取数据，失败打印错误"""
    try:
        df = _fetch_hist(symbol, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"[WARN] {symbol} 获取失败: {e}")
    return None


def fetch_stock_hist(symbol, use_cache=True):
    """
    获取单只股票/ETF历史日线数据（带增量缓存）
    """
    if not use_cache:
        return _fetch_from_api(symbol)

    # 1. 检查缓存
    today = datetime.now().strftime('%Y-%m-%d')
    last_cached = get_last_date(symbol)
    cached_df = load_hist(symbol)

    if last_cached and cached_df is not None and len(cached_df) >= 35:
        # 2. 缓存充足但数据量不足（如旧缓存只有180天），强制重新拉取
        if len(cached_df) < 350:
            df = _fetch_from_api(symbol)
            if df is not None and not df.empty:
                save_hist(symbol, df)
                return load_hist(symbol)

        # 3. 缓存充足，检查是否需要增量更新
        last_check = get_last_check(symbol)
        if last_check == today:
            return cached_df

        prev_td = _prev_trade_date()
        if last_cached >= today or last_cached >= prev_td:
            set_last_check(symbol, today)
            return cached_df

        # 3. 增量拉取
        new_df = _fetch_from_api(symbol, start_date=last_cached, end_date=today)
        set_last_check(symbol, today)
        if new_df is not None and not new_df.empty:
            save_hist(symbol, new_df)
            new_rows = new_df[~new_df['日期'].astype(str).isin(cached_df['日期'].astype(str))]
            if not new_rows.empty:
                cached_df = pd.concat([cached_df, new_rows], ignore_index=True)
            return cached_df
        return cached_df
    else:
        # 4. 无缓存或缓存不足
        last_check = get_last_check(symbol)
        if last_check == today:
            return cached_df

        df = _fetch_from_api(symbol)
        set_last_check(symbol, today)
        if df is not None and not df.empty:
            save_hist(symbol, df)
            return load_hist(symbol)
        return None


# ==================== 批量预加载 ====================

def prefetch_hist_batch(symbols, start_date=None, end_date=None, batch_size=50):
    """
    批量预加载历史数据到缓存
    - 无缓存: 拉全量180天
    - 缓存过时: 只拉增量(最后缓存日期~今天)
    多线程并发。
    """
    cached_set = get_cached_codes()
    no_cache = [s for s in symbols if s not in cached_set]

    # 检查缓存过时的（返回 {code: last_date}）
    prev_td = _prev_trade_date()
    stale_map = get_stale_codes(prev_td)
    stale_list = [s for s in symbols if s in stale_map]

    need_fetch = no_cache + stale_list

    if not need_fetch:
        print(f"[INFO] 全部 {len(symbols)} 只缓存已是最新，跳过预加载")
        return

    print(f"[INFO] 预加载: 无缓存{len(no_cache)}只(全量) + 过时{len(stale_list)}只(增量) (共{len(symbols)}只)...")

    today = datetime.now().strftime('%Y-%m-%d')
    fetched = 0
    failed = 0

    def _fetch_one(code):
        try:
            if code in stale_map:
                # 过时: 只拉增量
                s = stale_map[code]
                df = _fetch_hist(code, start_date=s, end_date=today)
            else:
                # 无缓存: 拉全量
                df = _fetch_hist(code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                save_hist(code, df)
                set_last_check(code, today)
                return True
        except Exception:
            pass
        return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, code): code for code in need_fetch}
        for f in as_completed(futures):
            if f.result():
                fetched += 1
            else:
                failed += 1
            done = fetched + failed
            if done % 100 == 0 or done == len(need_fetch):
                print(f"  预加载进度 {done}/{len(need_fetch)}，已缓存 {fetched} 只")

    if failed:
        print(f"[WARN] {failed} 只股票获取失败")
    print(f"[OK] 批量预加载完成，缓存 {fetched}/{len(need_fetch)} 只")
