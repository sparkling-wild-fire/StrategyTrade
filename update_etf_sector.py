# update_etf_sector.py — 更新ETF子行业分类
import pymysql
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

# 指数名称 → 子行业板块映射（细分到子行业级别）
INDEX_TO_SECTOR = {
    # === 宽基/指数 ===
    '上证50': '宽基', '上证指数': '宽基', '沪深300指数': '宽基',
    '中证500': '宽基', '中证1000': '宽基', '中证2000': '宽基',
    '国证2000': '宽基', '深证100': '宽基', '创业板指': '宽基',
    '创业板50': '宽基', '科创50': '宽基', '科创100': '宽基',
    '科创综指': '宽基', '中证A50': '宽基', '中证A500': '宽基',
    '科创创业50': '宽基',

    # === 科技-半导体 ===
    '半导体产品与设备': '半导体', '半导体材料设备': '半导体',
    '半导体芯片': '半导体', '科创芯片': '半导体', '芯片': '半导体',

    # === 科技-AI/软件 ===
    '人工智能': 'AI', '科创AI': 'AI', '大数据': 'AI',
    '云计算': 'AI', '计算机': '软件', '软件': '软件', '信创': '软件',

    # === 科技-通信/电子 ===
    '5G通信': '通信', '通信设备': '通信',
    '电子': '电子', '消费电子': '电子',
    '科技龙头': '科技',

    # === 科技-金融科技 ===
    '金融科技': '金融科技',

    # === 医药-细分 ===
    '创新药': '创新药', '生物科技': '创新药',
    '医疗': '医疗', '医疗器械': '医疗',
    '中药': '中药',

    # === 消费-细分 ===
    '消费': '消费', '白酒': '白酒', '酒': '白酒',
    '食品饮料': '食品', '细分食品': '食品',
    '家电': '家电', '旅游': '旅游',

    # === 金融-细分 ===
    '银行': '银行', '证券': '证券', '非银行金融': '证券',

    # === 周期-细分 ===
    '有色金属': '有色', '稀有金属': '有色', '稀土': '有色',
    '黄金股': '黄金', '钢铁': '钢铁', '煤炭': '煤炭',
    '细分化工': '化工', '建筑材料': '化工',

    # === 新能源-细分 ===
    '新能源': '新能源', '新能源车': '新能源车',
    '光伏': '光伏', '电池': '电池',
    '低碳': '新能源', '绿色电力': '绿电', '电力': '绿电',

    # === 制造-细分 ===
    '机器人': '机器人', '机器人产业': '机器人',
    '机床': '制造', '基建工程': '制造',

    # === 其他行业 ===
    '军工': '军工', '军工龙头': '军工', '国防': '军工',
    '农业': '农业', '畜牧养殖': '农业',
    '动漫游戏': '传媒', '传媒': '传媒',
    '房地产': '房产',

    # === 红利/策略/央企 ===
    '中证红利': '红利', '中证红利低波': '红利', '红利低波50': '红利',
    '300红利低波': '红利', '红利指数(上证)': '红利', '深证红利': '红利',
    '央企结构调整': '央企', '央企创新': '央企', '国企一带一路': '央企',
    '上海国企': '央企',
    '自由现金流': '策略', '成渝经济圈': '区域', '教育': '教育',
}


def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset='utf8mb4',
    )

    try:
        cursor = conn.cursor()

        # 更新板块分类
        updated = 0
        skipped = 0
        cursor.execute("SELECT etf_code, index_name FROM etf_info")
        rows = cursor.fetchall()
        for etf_code, index_name in rows:
            sector = INDEX_TO_SECTOR.get(index_name, '')
            if sector:
                cursor.execute("UPDATE etf_info SET sector=%s WHERE etf_code=%s", (sector, etf_code))
                updated += 1
            else:
                skipped += 1

        conn.commit()
        print(f'[OK] 更新 {updated} 只ETF板块，跳过 {skipped} 只')

        # 打印结果
        cursor.execute("SELECT sector, COUNT(*) FROM etf_info WHERE sector!='' GROUP BY sector ORDER BY COUNT(*) DESC")
        print('\n[子行业分布]')
        for sector, cnt in cursor.fetchall():
            cursor.execute("SELECT index_name FROM etf_info WHERE sector=%s LIMIT 2", (sector,))
            samples = [r[0] for r in cursor.fetchall()]
            print(f'  {sector}: {cnt}只 {samples}')

    finally:
        conn.close()


if __name__ == '__main__':
    main()
