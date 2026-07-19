import sys; sys.path.insert(0, 'D:/pythonProject/trade')
from market import fetch_stock_hist, fetch_spot_data
from factors import calculate_all
from strategies.aftermarket_strategy import score as score_stock
from factors.macd import score as score_macd
from factors.kdj import score as score_kdj
from factors.boll import score as score_boll
from factors.volume import score as score_vol
from factors.chase import score as score_chase
import pandas as pd

code = '513040'
spot = fetch_spot_data()
df = fetch_stock_hist(code)
if spot and code in spot:
    today_bar = spot[code]
    last_date = str(df.iloc[-1].iloc[0])
    if last_date < today_bar['日期']:
        df = pd.concat([df, pd.DataFrame([today_bar])], ignore_index=True)

df_ind = calculate_all(df)
c = df_ind.iloc[-1]

print('=== 513040 ===')
print(f'date={c.iloc[0]} close={c["收盘"]:.3f}')
print(f'MA5={c["MA5"]:.3f} MA10={c["MA10"]:.3f} MA20={c["MA20"]:.3f}')
print(f'BOLL U={c["BBU_20_2.0"]:.3f} M={c["BBM_20_2.0"]:.3f} L={c["BBL_20_2.0"]:.3f}')
print()
print('--- price 15d ---')
for _, r in df_ind.tail(15).iterrows():
    print(f'{r.iloc[0]} C={r["收盘"]:.3f} V={r["成交量"]:.0f}')
print()
print('--- MACD/KDJ 10d ---')
for _, r in df_ind.tail(10).iterrows():
    print(f'{r.iloc[0]} DIF={r["MACD_12_26_9"]:.4f} DEA={r["MACDs_12_26_9"]:.4f} H={r["MACDh_12_26_9"]:.4f} K={r["STOCHk_9_3_3"]:.1f} D={r["STOCHd_9_3_3"]:.1f} J={r["J_9_3_3"]:.1f}')
print()
macd_s, macd_d = score_macd(df_ind)
kdj_s, kdj_d = score_kdj(df_ind)
bb_s, bb_d = score_boll(df_ind)
vol_s, vol_d = score_vol(df_ind)
chase_s, chase_d = score_chase(df_ind)
result = score_stock(df_ind)
print(f'MACD={macd_s} {macd_d}')
print(f'KDJ={kdj_s} {kdj_d}')
print(f'BB={bb_s} {bb_d}')
print(f'VOL={vol_s} {vol_d}')
print(f'CHASE={chase_s} {chase_d}')
print(f'total={result["total"]} rating={result["rating"]}')
print(f'details: {";".join(result["details"])}')
