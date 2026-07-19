# fundamental_filter.py
import traceback
from config import PE_MAX


def _filter_by_jqdata(codes, date=None):
    """通过JQData批量获取PE，返回 {code: pe_ratio}"""
    try:
        from JQData import ensure_auth, to_jqcode, from_jqcode
        import jqdatasdk as jq
        ensure_auth()

        # JQData账号有效期有限，使用固定日期避免超出范围
        # 先尝试获取最近交易日，失败则用2026-04-10（账号有效期内）
        end_date = '2026-04-10'
        try:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            days = jq.get_trade_days(end_date=today, count=5)
            if len(days) > 0:
                candidate = str(days[-1])
                # 检查是否在有效期内（2026-04-15之前）
                if candidate <= '2026-04-15':
                    end_date = candidate
        except Exception:
            pass

        # JQData限制每次最多3000只
        jqcodes = [to_jqcode(c) for c in codes]
        batch_size = 3000
        result = {}
        for i in range(0, len(jqcodes), batch_size):
            batch = jqcodes[i:i + batch_size]
            df = jq.get_valuation(batch, end_date=end_date, count=1,
                                  fields=['code', 'pe_ratio'])
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = from_jqcode(row['code'])
                    pe = row['pe_ratio']
                    if pe is not None and str(pe) != 'nan':
                        result[code] = float(pe)
        return result
    except Exception as e:
        print(f"[WARN] JQData基本面获取失败: {e}")
        return None


def _filter_by_akshare(codes):
    """通过akshare获取PE（降级方案），返回 {code: pe_ratio}"""
    try:
        import akshare as ak
        from utils import retry_with_backoff
        df = retry_with_backoff(ak.stock_zh_a_spot_em)
        if df is None or df.empty:
            return None
        # akshare EM列名: 代码, 市盈率-动态
        col_pe = None
        for c in df.columns:
            if '市盈' in c or 'pe' in c.lower():
                col_pe = c
                break
        if col_pe is None:
            return None
        code_set = set(str(c) for c in codes)
        result = {}
        for _, row in df.iterrows():
            code = str(row['代码'])
            if code in code_set:
                try:
                    pe = float(row[col_pe])
                    result[code] = pe
                except (ValueError, TypeError):
                    pass
        return result
    except Exception as e:
        print(f"[WARN] akshare基本面获取失败: {e}")
        return None


def filter_by_fundamentals(code_name_list, enabled=True):
    """
    基本面前置过滤，剔除PE不合格的标的

    参数:
        code_name_list: [(code, name), ...]
        enabled: 是否启用过滤

    返回:
        filtered_list: [(code, name), ...]
        excluded_count: 被剔除的数量
    """
    if not enabled:
        print("[INFO] 基本面过滤已禁用，跳过")
        return code_name_list, 0

    codes = [c for c, _ in code_name_list]
    print(f"[INFO] 基本面过滤: 获取 {len(codes)} 只股票的PE数据...")

    # 优先JQData，降级akshare
    pe_map = _filter_by_jqdata(codes)
    source = 'JQData'
    if pe_map is None:
        pe_map = _filter_by_akshare(codes)
        source = 'akshare'
    if pe_map is None:
        print("[WARN] 基本面数据获取全部失败，跳过过滤")
        return code_name_list, 0

    print(f"[OK] 基本面数据获取成功({source})，{len(pe_map)} 只有PE数据")

    filtered = []
    excluded = 0
    for code, name in code_name_list:
        pe = pe_map.get(code)
        if pe is None:
            # 无PE数据的保留（可能是新股或ETF）
            filtered.append((code, name))
            continue
        if pe <= 0:
            # 亏损股剔除
            excluded += 1
            continue
        if pe > PE_MAX:
            # PE过高剔除
            excluded += 1
            continue
        filtered.append((code, name))

    print(f"[OK] 基本面过滤完成: 保留 {len(filtered)} 只，剔除 {excluded} 只(亏损或PE>{PE_MAX})")
    return filtered, excluded
