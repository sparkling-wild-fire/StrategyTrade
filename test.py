# test.py — 测试JQData交易日查询
import jqdatasdk as jq
from config import JQ_USERNAME, JQ_PASSWORD
from datetime import datetime


def main():
    print("1. 登录JQData...")
    jq.auth(JQ_USERNAME, JQ_PASSWORD)
    print(f"   认证状态: {jq.is_auth()}")

    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n2. 今天: {today}")

    print("\n3. 查询最近5个交易日 (end_date=今天):")
    try:
        days = jq.get_trade_days(end_date=today, count=5)
        for d in days:
            print(f"   {d}")
        print(f"   最新交易日: {days[-1]}")
    except Exception as e:
        print(f"   失败: {e}")

    print("\n4. 查询最近5个交易日 (end_date=2026-07-15):")
    try:
        days = jq.get_trade_days(end_date='2026-07-15', count=5)
        for d in days:
            print(f"   {d}")
        print(f"   最新交易日: {days[-1]}")
    except Exception as e:
        print(f"   失败: {e}")

    print("\n5. 查询2026-04-10~2026-07-15之间的交易日:")
    try:
        days = jq.get_trade_days(start_date='2026-04-10', end_date='2026-07-15')
        print(f"   共{len(days)}个交易日")
        if days:
            print(f"   最后5个: {days[-5:]}")
    except Exception as e:
        print(f"   失败: {e}")

    print("\n6. 尝试获取600048最新行情:")
    try:
        df = jq.get_price('600048.XSHG', end_date=today, count=5,
                          fields=['open', 'close', 'high', 'low', 'volume'],
                          frequency='daily', skip_paused=True, fq='pre')
        print(df)
    except Exception as e:
        print(f"   失败: {e}")


if __name__ == "__main__":
    main()
