# config.py
import warnings

# 忽略警告
warnings.filterwarnings("ignore")


def _load_db_config():
    """从MySQL sys_config表加载敏感配置"""
    import pymysql
    try:
        # conn = pymysql.connect(
        #     host='127.0.0.1', port=3306,
        #     user='root', password='root',
        #     database='stock_data', charset='utf8mb4',
        # )
        conn = pymysql.connect(
            host='rm-bp1j3918m2i40w4o3go.mysql.rds.aliyuncs.com', port=3306,
            user='trade', password='1520ZT56jx',
            database='dbtrade', charset='utf8mb4',
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT config_key, config_value FROM sys_config")
                return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception:
        return {}


_db_cfg = _load_db_config()


def _cfg(key, default=''):
    """从数据库读取配置，读取失败返回默认值"""
    return _db_cfg.get(key, default)


# 请求头伪装
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.sina.com.cn/',
    'Connection': 'keep-up'
}

# 重试配置
MAX_RETRIES = 3
BASE_DELAY = 1.0  # 基础延迟秒数
MAX_DELAY = 30.0  # 最大延迟秒数

# 筛选条件
# 60=沪市主板 00=深市主板 30=创业板 68=科创板
STOCK_PREFIXES = ('60', '00', '30', '68')
# ETF代码前缀：51/52/53/56/58=沪市ETF 15/16=深市ETF
ETF_PREFIXES = ('51', '52', '53', '56', '58', '15', '16')
EXCLUDE_ST = True           # 是否排除ST股

# 以下配置从数据库 sys_config 表读取
JQ_USERNAME = _cfg('JQ_USERNAME')
JQ_PASSWORD = _cfg('JQ_PASSWORD')

MYSQL_HOST = _cfg('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(_cfg('MYSQL_PORT', '3306'))
MYSQL_USER = _cfg('MYSQL_USER', 'root')
MYSQL_PASSWORD = _cfg('MYSQL_PASSWORD', 'root')
MYSQL_DB = _cfg('MYSQL_DB', 'stock_data')

FEISHU_WEBHOOK_URL = _cfg('FEISHU_WEBHOOK_URL')
FEISHU_APP_ID = _cfg('FEISHU_APP_ID')
FEISHU_APP_SECRET = _cfg('FEISHU_APP_SECRET')

# 卖出信号：传入需要计算卖出信号的证券/ETF代码列表，默认为空不计算
# 示例: SALE_CODES = ['600048', '510300', '159915']
SALE_CODES = []

# 基本面过滤
FUNDAMENTAL_FILTER_ENABLED = True
PE_MAX = 200  # PE超过此值剔除（亏损股PE<=0也剔除）

# 市场环境检测
MARKET_ENV_ENABLED = True
BEAR_BUY_THRESHOLD = 4  # 熊市时买入阈值提高到4
