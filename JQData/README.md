# JQData 接口文档

> 官方文档：https://www.joinquant.com/help/api/doc?name=JQDatadoc
>
> 本项目封装模块：`JQData/jqdata_client.py`
>
> 账号有效期：2025-04-06 至 2026-04-13

---

## 1. 认证

### `ensure_auth()`
确保JQData已认证，未认证则自动使用 `config.py` 中的账号密码登录。

---

## 2. 代码格式转换

### `to_jqcode(symbol) → str`
纯数字代码转聚宽格式。

| 输入 | 输出 | 规则 |
|------|------|------|
| `'600048'` | `'600048.XSHG'` | 60/68开头 → 沪市 |
| `'000001'` | `'000001.XSHE'` | 00/30开头 → 深市 |
| `'600048.XSHG'` | `'600048.XSHG'` | 已含后缀则原样返回 |

### `from_jqcode(jqcode) → str`
聚宽格式代码转纯数字。

| 输入 | 输出 |
|------|------|
| `'600048.XSHG'` | `'600048'` |
| `'000001.XSHE'` | `'000001'` |

---

## 3. 股票列表

### `get_stock_list(date=None) → DataFrame`

获取全市场A股列表（沪市主板60 / 科创板68 / 深市主板00 / 创业板30）。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| date | str | 查询日期，默认 `'2026-04-10'`（账号有效期内） |

**返回：** DataFrame

| 列名 | 类型 | 说明 |
|------|------|------|
| 代码 | str | 纯数字代码（如 `600048`） |
| 名称 | str | 股票名称（如 `保利发展`） |

**底层API：** `jqdatasdk.get_all_securities(types='stock', date=date)`

**示例：**
```python
from JQData import get_stock_list
df = get_stock_list()
#      代码    名称
# 0  600000  浦发银行
# 1  000001  平安银行
```

---

## 4. 历史行情

### `get_price(symbol, start_date=None, end_date=None, frequency='daily', fq='pre') → DataFrame`

获取单只股票历史行情数据。

**参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| symbol | str | 必填 | 纯数字股票代码（如 `'600048'`） |
| start_date | str | None | 开始日期 `'YYYY-MM-DD'` |
| end_date | str | None | 结束日期 `'YYYY-MM-DD'` |
| frequency | str | `'daily'` | 频率：`'daily'` 日线 / `'minute'` 分钟线 |
| fq | str | `'pre'` | 复权方式：`'pre'` 前复权 / `'post'` 后复权 / `None` 不复权 |

**返回：** DataFrame，失败返回 None

| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | str | `'YYYY-MM-DD'` |
| 开盘 | float | 开盘价 |
| 收盘 | float | 收盘价 |
| 最高 | float | 最高价 |
| 最低 | float | 最低价 |
| 成交量 | float | 成交量（股） |

**底层API：** `jqdatasdk.get_price(code, start_date, end_date, frequency, fields, skip_paused=True, fq=fq)`

**示例：**
```python
from JQData import get_price
df = get_price('000001', start_date='2026-04-01', end_date='2026-04-10')
#         日期    开盘    收盘    最高    最低        成交量
# 0  2026-04-01  10.74  10.79  10.87  10.73   94916425.0
```

---

## 5. 行业分类

### `get_industry(symbols, date=None) → dict`

批量获取股票行业分类，返回多套分类体系（聚宽一级/二级、申万一级/二级/三级、证监会）。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| symbols | str 或 list | 纯数字代码或聚宽格式代码 |
| date | str | 查询日期，默认 `'2026-04-10'` |

**返回：** dict

```python
{
    '600048': {
        'jq_l1': {'industry_code': 'HY011', 'industry_name': '房地产'},
        'jq_l2': {'industry_code': 'HY11101', 'industry_name': '房地产开发'},
        'sw_l1': {'industry_code': '801180', 'industry_name': '房地产I'},
        'sw_l2': {'industry_code': '801181', 'industry_name': '房地产开发II'},
        'sw_l3': {'industry_code': '851811', 'industry_name': '房地产开发III'},
        'zjw': {'industry_code': 'K70', 'industry_name': '房地产业'},
    },
    ...
}
```

**底层API：** `jqdatasdk.get_industry(security, date=date)`

### `get_industries(name='sw_l1', date=None) → DataFrame`

获取行业分类列表。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| name | str | 分类标准：`'sw_l1'`/`'sw_l2'`/`'sw_l3'`/`'jq_l1'`/`'jq_l2'`/`'zjw'` |
| date | str | 查询日期 |

**返回：** DataFrame，列为 `name`(行业名), `start_date`

---

## 6. 概念板块

### `get_concept(symbol, date=None) → dict`

获取股票所属概念板块。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| symbol | str | 纯数字或聚宽格式代码 |
| date | str | 查询日期 |

**返回：** dict

```python
{
    '300750': {
        'jq_concept': [
            {'concept_code': 'SC0044', 'concept_name': '特斯拉'},
            {'concept_code': 'SC0390', 'concept_name': '锂电池概念'},
            ...
        ]
    }
}
```

**底层API：** `jqdatasdk.get_concept(security, date=date)`

---

## 7. 交易日

### `get_trade_days(start_date=None, end_date=None) → list`

获取指定日期范围内的所有交易日。

**返回：** 日期列表，如 `[datetime.date(2026, 7, 1), datetime.date(2026, 7, 2), ...]`

### `get_prev_trade_date(ref_date=None) → str`

获取指定日期的上一个交易日（排除当天）。

**返回：** 字符串，如 `'2026-07-14'`

---

## 8. ST状态

### `get_is_st(symbols, date=None) → dict`

查询股票是否为ST股。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| symbols | list | 纯数字或聚宽格式代码列表 |
| date | str | 查询日期 |

**返回：** dict，如 `{'000001': False, '600000': True}`

**底层API：** `jqdatasdk.get_extras('is_st', security_list, start_date, end_date)`

---

## 9. 市值数据

### `get_valuation(symbol, date=None, fields=None) → DataFrame`

获取股票市值数据。

**常用字段：**

| 字段 | 说明 |
|------|------|
| `code` | 股票代码 |
| `day` | 日期 |
| `market_cap` | 总市值（亿元） |
| `circulating_market_cap` | 流通市值（亿元） |
| `pe_ratio` | 市盈率 TTM |
| `pb_ratio` | 市净率 |
| `turnover_ratio` | 换手率 |

**底层API：** `jqdatasdk.get_valuation(security_list, end_date, count, fields)`

---

## 10. 本项目数据获取优先级

| 数据 | 优先级 | 降级方案 |
|------|--------|----------|
| 股票列表 | **JQData** `get_all_securities` | akshare 东方财富 → 新浪财经 |
| 历史行情 | **JQData** `get_price` | akshare 腾讯 → 东方财富 |
| 行业分类 | **JQData** `get_industry` | 无（akshare东方财富接口不稳定） |
| 概念板块 | **JQData** `get_concept` | 无 |
| 交易日 | **JQData** `get_trade_days` | 本地估算（跳过周末） |
| ST状态 | **JQData** `get_extras('is_st')` | 名称包含"ST"判断 |
