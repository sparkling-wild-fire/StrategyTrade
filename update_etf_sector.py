# update_etf_sector.py — 给etf_info表添加所属板块字段并写入数据
import pymysql
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

# 指数名称 → 所属板块映射
# 基于etf_info表中现有的200只ETF的指数名称分类
INDEX_TO_SECTOR = {
    # === 宽基/指数 ===
    '上证50': '宽基',
    '上证指数': '宽基',
    '沪深300指数': '宽基',
    '中证500': '宽基',
    '中证1000': '宽基',
    '中证2000': '宽基',
    '国证2000': '宽基',
    '深证100': '宽基',
    '创业板指': '宽基',
    '创业板50': '宽基',
    '科创50': '宽基',
    '科创100': '宽基',
    '科创综指': '宽基',
    '中证A50': '宽基',
    '中证A500': '宽基',
    '科创创业50': '宽基',

    # === 科技 ===
    '科技龙头': '科技',
    '半导体产品与设备': '科技',
    '半导体材料设备': '科技',
    '半导体芯片': '科技',
    '科创芯片': '科技',
    '科创AI': '科技',
    '芯片': '科技',
    '计算机': '科技',
    '软件': '科技',
    '信创': '科技',
    '5G通信': '科技',
    '通信设备': '科技',
    '电子': '科技',
    '消费电子': '科技',
    '人工智能': '科技',
    '云计算': '科技',
    '大数据': '科技',
    '金融科技': '科技',

    # === 医药 ===
    '医疗': '医药',
    '医疗器械': '医药',
    '创新药': '医药',
    '生物科技': '医药',
    '中药': '医药',

    # === 消费 ===
    '消费': '消费',
    '细分食品': '消费',
    '食品饮料': '消费',
    '白酒': '消费',
    '酒': '消费',
    '家电': '消费',
    '旅游': '消费',
    '消费电子': '科技',  # 消费电子归科技

    # === 金融 ===
    '银行': '金融',
    '证券': '金融',
    '非银行金融': '金融',

    # === 周期/资源 ===
    '有色金属': '周期',
    '稀有金属': '周期',
    '稀土': '周期',
    '钢铁': '周期',
    '煤炭': '周期',
    '黄金股': '周期',
    '细分化工': '周期',
    '建筑材料': '周期',

    # === 新能源/制造 ===
    '新能源': '新能源',
    '新能源车': '新能源',
    '光伏': '新能源',
    '电池': '新能源',
    '低碳': '新能源',
    '绿色电力': '新能源',
    '电力': '新能源',
    '基建工程': '制造',
    '机床': '制造',
    '机器人': '制造',
    '机器人产业': '制造',

    # === 军工 ===
    '军工': '军工',
    '军工龙头': '军工',
    '国防': '军工',

    # === 农业 ===
    '农业': '农业',
    '畜牧养殖': '农业',

    # === 房产 ===
    '房地产': '房产',

    # === 红利/策略 ===
    '中证红利': '红利',
    '中证红利低波': '红利',
    '红利低波50': '红利',
    '300红利低波': '红利',
    '红利指数(上证)': '红利',
    '深证红利': '红利',

    # === 传媒/游戏 ===
    '传媒': '传媒',
    '动漫游戏': '传媒',

    # === 其他 ===
    '央企结构调整': '央企',
    '央企创新': '央企',
    '国企一带一路': '央企',
    '上海国企': '央企',
    '自由现金流': '策略',
    '成渝经济圈': '区域',
    '教育': '教育',
}


def main():
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset='utf8mb4',
    )

    try:
        cursor = conn.cursor()

        # 1. 添加字段（如果不存在）
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME='etf_info' AND COLUMN_NAME='sector'
        """, (MYSQL_DB,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE etf_info ADD COLUMN sector VARCHAR(20) DEFAULT '' COMMENT '所属板块'")
            print("[OK] 添加 sector 字段")
        else:
            print("[INFO] sector 字段已存在")

        # 2. 根据指数名称更新板块
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
                print(f"  [SKIP] {etf_code} 指数={index_name} 未匹配板块")

        conn.commit()
        print(f"\n[OK] 更新 {updated} 只ETF板块，跳过 {skipped} 只")

        # 3. 打印结果
        cursor.execute("SELECT sector, COUNT(*) FROM etf_info WHERE sector!='' GROUP BY sector ORDER BY COUNT(*) DESC")
        print("\n[板块分布]")
        for sector, cnt in cursor.fetchall():
            print(f"  {sector}: {cnt}只")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
