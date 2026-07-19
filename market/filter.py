# stock_filter.py
import pymysql
import pandas as pd
from config import STOCK_PREFIXES, ETF_PREFIXES, EXCLUDE_ST
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB


def filter_a_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """筛选全市场A股（沪市主板60/深市主板00/创业板30/科创板68），可选排除ST股"""
    mask = df['代码'].str.startswith(STOCK_PREFIXES)
    if EXCLUDE_ST:
        mask &= ~df['名称'].str.contains('ST', case=False)
    filtered = df[mask][['代码', '名称']].copy().reset_index(drop=True)
    print(f"[OK] 筛选完成：从 {len(df)} 只股票中选出 {len(filtered)} 只A股")
    return filtered


def get_etf_list():
    """从MySQL etf_info表获取ETF列表"""
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset='utf8mb4',
    )
    try:
        df = pd.read_sql_query(
            "SELECT etf_code AS 代码, etf_name AS 名称, index_code AS 指数代码, index_name AS 指数名称, "
            "sector AS 所属板块 "
            "FROM etf_info ORDER BY etf_code",
            conn,
        )
    finally:
        conn.close()
    print(f"[OK] 从etf_info表获取 {len(df)} 只ETF")
    return df
