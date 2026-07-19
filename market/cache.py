# stock_cache.py
import pymysql
import pandas as pd
from queue import Queue
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

_POOL_SIZE = 10
_pool = Queue(maxsize=_POOL_SIZE)


def _get_conn():
    """从连接池获取连接"""
    try:
        conn = _pool.get_nowait()
        if conn.open:
            return conn
    except Exception:
        pass
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset='utf8mb4',
        autocommit=False,
    )


def _return_conn(conn):
    """归还连接到池"""
    try:
        if conn.open:
            _pool.put_nowait(conn)
            return
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def get_last_date(code):
    """获取某只股票在缓存中的最新日期，无数据返回None"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) FROM trade_hishq WHERE code = %s", (code,))
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    finally:
        _return_conn(conn)


def get_last_check(code):
    """获取上次增量检查日期，无返回None"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT last_check FROM trade_check_record WHERE code = %s", (code,))
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    finally:
        _return_conn(conn)


def set_last_check(code, date_str):
    """记录增量检查日期"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "REPLACE INTO trade_check_record (code, last_check) VALUES (%s, %s)",
                (code, date_str),
            )
        conn.commit()
    finally:
        _return_conn(conn)


def save_hist(code, df):
    """将历史数据写入缓存（REPLACE跳过重复日期）"""
    if df is None or df.empty:
        return
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            rows = [
                (code, str(r['日期']), r['开盘'], r['收盘'], r['最高'], r['最低'], r['成交量'])
                for _, r in df.iterrows()
            ]
            cur.executemany(
                "REPLACE INTO trade_hishq (code, date, open, close, high, low, volume) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)", rows,
            )
        conn.commit()
    finally:
        _return_conn(conn)


def load_hist(code, min_rows=35):
    """从缓存读取历史数据，不足min_rows行返回None"""
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT date AS 日期, open AS 开盘, close AS 收盘, "
            "high AS 最高, low AS 最低, volume AS 成交量 "
            "FROM trade_hishq WHERE code = %s ORDER BY date",
            conn, params=(code,),
        )
    finally:
        _return_conn(conn)
    if len(df) < min_rows:
        return None
    return df


def get_cached_codes(min_rows=35):
    """获取缓存中已有且数据量>=min_rows的股票代码集合"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code FROM trade_hishq GROUP BY code HAVING COUNT(*) >= %s",
                (min_rows,),
            )
            return {r[0] for r in cur.fetchall()}
    finally:
        _return_conn(conn)


def get_stale_codes(min_date):
    """获取缓存最新日期早于min_date的代码及最后日期（数据过时需要刷新）"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code, MAX(date) FROM trade_hishq GROUP BY code HAVING MAX(date) < %s",
                (min_date,),
            )
            return {r[0]: str(r[1]) for r in cur.fetchall()}
    finally:
        _return_conn(conn)
