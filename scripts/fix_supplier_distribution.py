"""
中分類ごとのサプライヤ分布を修正:
  1社: 20% (8カテゴリ)
  2社: 60% (24カテゴリ)
  3社: 20% (8カテゴリ) ← 3社以上の代表値として3を使用
"""
import pandas as pd

INPUT = "data/samples/po_transactions_v4.csv"

df = pd.read_csv(INPUT)

# supplier_parent_name → supplier_parent_id のマッピング
sup_id_map = (
    df.drop_duplicates("supplier_parent_name")
    .set_index("supplier_parent_name")["supplier_parent_id"]
    .to_dict()
)

# 中分類を名前順にソートして固定順序で割り当て
cats = sorted(df["item_cat_m_name"].dropna().unique())  # 40個

# 割り当て: 1社=8, 2社=24, 3社=8 (合計40)
#   先頭8個→3社, 次24個→2社, 末尾8個→1社
n_3 = 8
n_2 = 24
# n_1 = 8 (残り)

targets: dict[str, int] = {}
for i, cat in enumerate(cats):
    if i < n_3:
        targets[cat] = 3
    elif i < n_3 + n_2:
        targets[cat] = 2
    else:
        targets[cat] = 1

print("=== 割り当て ===")
for cat, n in targets.items():
    print(f"  {n}社 : {cat}")

# 修正: 各中分類で支出上位N社を残し、それ以外は上位1社に置換
df_new = df.copy()

for cat, target_n in targets.items():
    mask = df_new["item_cat_m_name"] == cat
    cat_rows = df_new[mask]

    # 支出上位 target_n 社を確保
    top_sups = (
        cat_rows.groupby("supplier_parent_name")["net_amount"]
        .sum()
        .sort_values(ascending=False)
        .head(target_n)
        .index.tolist()
    )
    top_sup = top_sups[0]  # 置換先: 最大支出サプライヤ

    # 上位以外の行を top_sup に書き換え
    non_top = mask & ~df_new["supplier_parent_name"].isin(top_sups)
    df_new.loc[non_top, "supplier_parent_name"] = top_sup
    df_new.loc[non_top, "supplier_parent_id"] = sup_id_map.get(top_sup, "")

# 検証
med_sup = df_new.groupby("item_cat_m_name")["supplier_parent_name"].nunique()
vc = med_sup.value_counts().sort_index()
total = len(med_sup)
print("\n=== 修正後の分布 ===")
for n, cnt in vc.items():
    pct = cnt / total * 100
    print(f"  {n}社: {cnt}カテゴリ ({pct:.0f}%)")

print("\n=== 中分類ごとの確認 ===")
for cat in cats:
    n = med_sup[cat]
    sups = df_new[df_new["item_cat_m_name"] == cat]["supplier_parent_name"].unique().tolist()
    print(f"  [{n}社] {cat}: {', '.join(sups[:3])}{'...' if n > 3 else ''}")

df_new.to_csv(INPUT, index=False, encoding="utf-8")
print(f"\n保存完了: {INPUT}")
