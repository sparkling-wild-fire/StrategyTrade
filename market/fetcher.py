import os

# V8(PartitionAlloc)在Python 3.11多线程下会崩溃，主线程提前初始化避免重复初始化
try:
    from py_mini_racer import MiniRacer
    MiniRacer().execute('1')
except Exception:
    pass

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import retry_with_backoff
from market.cache import get_last_date, get_last_check, set_last_check, save_hist, load_hist, get_cached_codes, get_stale_codes, _get_conn as _get_db_conn, _return_conn as _return_db_conn
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
    """获取最新可用数据的日期（盘后/周末返回最近交易日，盘中返回前一交易日）"""
    now = datetime.now()
    if _is_market_closed():
        # 已收盘或周末：返回最近的交易日（当天或之前最后一个工作日）
        d = now
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.strftime('%Y-%m-%d')
    # 盘中：前一交易日
    d = now - timedelta(days=1)
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
    """获取A股列表：优先从stock_info表读取，失败则走API"""
    from config import STOCK_PREFIXES
    try:
        conn = _get_db_conn()
        df = pd.read_sql_query(
            "SELECT code AS 代码, name AS 名称 FROM stock_info", conn,
        )
        _return_db_conn(conn)
        if not df.empty:
            print(f"[OK] 从stock_info表获取 {len(df)} 只A股")
            return df
    except Exception as e:
        print(f"[WARN] stock_info表读取失败: {e}，回退到API...")

    try:
        print("[INFO] 从新浪财经获取股票列表...")
        df = retry_with_backoff(fetch_stock_list_sina)
        print(f"[OK] 成功获取 {len(df)} 只股票")
        return df

    try:
        print("[INFO] 从新浪财经获取股票列表...")
        df = retry_with_backoff(fetch_stock_list_sina)
        print(f"[OK] 成功获取 {len(df)} 只股票")
        return df
    except Exception as e:
        print(f"[ERR] 新浪财经获取失败: {e}")
        raise


# ==================== 盘中实时行情 ====================

def _is_market_closed():
    """判断当前是否已收盘（15:05后视为收盘）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return True
    return now.hour > 15 or (now.hour == 15 and now.minute >= 5)


def _fetch_spot_from_db():
    """从数据库trade_hishq获取最新一条记录作为行情数据"""
    conn = _get_db_conn()
    try:
        sql = (
            "SELECT h.code, h.date, h.open, h.close, h.high, h.low, h.volume "
            "FROM trade_hishq h "
            "INNER JOIN (SELECT code, MAX(date) AS max_date FROM trade_hishq GROUP BY code) m "
            "ON h.code = m.code AND h.date = m.max_date"
        )
        df = pd.read_sql_query(sql, conn)
    finally:
        _return_db_conn(conn)

    if df.empty:
        return {}

    spot = {}
    for _, r in df.iterrows():
        try:
            spot[str(r['code'])] = {
                '日期': str(r['date']),
                '开盘': float(r['open']),
                '收盘': float(r['close']),
                '最高': float(r['high']),
                '最低': float(r['low']),
                '成交量': float(r['volume']),
            }
        except (ValueError, TypeError):
            continue
    return spot


def fetch_spot_data():
    """获取全市场行情数据：盘后从数据库读取，盘中走API"""
    if _is_market_closed():
        print("[INFO] 盘后模式：从数据库读取最新行情...")
        spot = _fetch_spot_from_db()
        if spot:
            print(f"[OK] 数据库行情 {len(spot)} 只")
            return spot
        print("[WARN] 数据库无行情数据，回退到API...")

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
