"""取得した楽天商品から、記事に載せる候補を選ぶ。

rakuten_fetch.py の生データはそのままでは使えない(実データで確認済み):
  - 商品名の頭に販促文が付く。「【条件達成で最大8000ポイント還元！...8/25 0:00~】」
    のような期限付き文言をそのまま載せると、期限切れ後に嘘の表示になる。
  - ジャンル内にもランニング用途でない品が混ざる(例: ナイキ エア リフト)。
  - 同一モデルが別ショップで重複する。

方針(オーナー決定): 主要ブランド限定 + 価格/レビュー件数の下限 の併用。
初心者向け記事のため、サイズ展開とサポートが期待できるブランド品に絞る。

使い方:
    python scripts/select_items.py
    python scripts/select_items.py --min-price 4000 --min-reviews 100 --top 8
"""
import argparse
import json
import re
import unicodedata

# 表記ゆれを吸収するため、正規化後の小文字表記で照合する
BRANDS = {
    "ミズノ": ["ミズノ", "mizuno"],
    "アシックス": ["アシックス", "asics"],
    "ナイキ": ["ナイキ", "nike"],
    "アディダス": ["アディダス", "adidas"],
    "ニューバランス": ["ニューバランス", "new balance", "newbalance"],
    "プーマ": ["プーマ", "puma"],
    "ブルックス": ["ブルックス", "brooks"],
    "ホカ": ["ホカ", "hoka"],
    "サッカニー": ["サッカニー", "saucony"],
    "オン": ["on running", "オンランニング"],
}

# ランニング用途でない品を除く。ジャンルが「ランニング>シューズ」でも混入する。
EXCLUDE_KEYWORDS = [
    "エア リフト", "air rift",          # トレーニング/ライフスタイル向け
    "サンダル", "スリッパ", "上履き",
    "キッズ", "ジュニア", "子供", "こども",
    "インソール", "靴紐", "靴ひも", "シューレース",
    "シューズケース", "シューズバッグ", "収納",
    "スパイク", "野球", "サッカー", "バスケ",
    "ライフスタイル",  # ランニング用でない系列(アディダスの表記で実際に混入した)
]

# 商品名の先頭・末尾に付く販促文。期限付きの文言が混ざるため必ず落とす。
PROMO_PATTERNS = [
    r"【[^】]*】",
    r"＼[^／]*／",
    r"\([^)]*ポイント[^)]*\)",
    r"^[\s　]*[!！★☆]+",
]

# 括弧で囲まれていない販促文・注記。実データで残っていたものを列挙する。
NOISE_PHRASES = [
    "期間限定", "送料無料", "土日も発送", "翌日配達", "あす楽", "在庫限り",
    "returnable", "返品可", "返品不可", "ラッピング不可", "ラッピング対応",
    "サイズ交換無料", "動画あり", "公式", "正規品", "セール", "限定価格",
    "楽天ランキング", "冠達成", "最安値挑戦", "新作", "即納",
]
NOISE_PATTERNS = [
    r"\d+\s*%\s*off",
    r"\d+[,\d]*円\s*→\s*\d+[,\d]*円",
]

# 重複判定の際に無視する語(同一モデルの派生を1件にまとめるため)
VARIANT_WORDS = [
    "メンズ", "レディース", "レディス", "レディーズ", "ウィメンズ", "ユニセックス",
    "男女兼用", "ワイド", "幅広", "スーパーワイド", "レギュラー", "wide",
]
MODEL_CODE = re.compile(r"\b[a-z]{1,3}\d{3,5}-?\d{0,3}\b")


def normalize(text):
    """全角/半角・大文字小文字を吸収した照合用の文字列。"""
    return unicodedata.normalize("NFKC", text or "").lower()


def clean_name(name):
    """販促文を落として商品名だけにする。"""
    s = name
    for _ in range(6):  # 入れ子・連続した括弧を繰り返し除去
        before = s
        for pat in PROMO_PATTERNS:
            s = re.sub(pat, " ", s)
        if s == before:
            break
    for phrase in NOISE_PHRASES:
        s = s.replace(phrase, " ")
    for pat in NOISE_PATTERNS:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" 　-–—/／|｜!！★☆、,")
    return s


def detect_brand(name):
    n = normalize(name)
    for brand, aliases in BRANDS.items():
        if any(normalize(a) in n for a in aliases):
            return brand
    return None


def model_signature(brand, name):
    """同一モデルの重複排除用キー。

    ブランド名 + 商品名から拾った英数字トークン(型番・モデル名)の先頭2つで判定する。
    完全ではないので、除外された件数を必ず表示して目視できるようにする。
    """
    n = normalize(name)
    n = MODEL_CODE.sub(" ", n)                      # 型番はショップごとに異なるため無視
    for w in VARIANT_WORDS:                          # メンズ/ワイド等の派生を同一視
        n = n.replace(normalize(w), " ")
    tokens = re.findall(r"[a-z]+ ?\d+(?:\.\d+)?|[a-z]{3,}|\d{2,}", n)
    skip = {"running", "shoes", "run", "size", "cm", normalize(brand)}
    skip |= {normalize(a) for aliases in BRANDS.values() for a in aliases}
    tokens = [t for t in tokens if t not in skip]
    return (brand, " ".join(tokens[:2]))


def main():
    p = argparse.ArgumentParser(description="記事掲載候補の選定")
    p.add_argument("--src", default="data/running_shoes.json")
    p.add_argument("--out", default="data/running_shoes_selected.json")
    p.add_argument("--min-price", type=int, default=4000, help="この価格未満は初心者向けとして除外")
    p.add_argument("--min-reviews", type=int, default=100)
    p.add_argument("--min-average", type=float, default=4.0)
    p.add_argument("--max-price", type=int, default=None,
                   help="価格上限。既定は無制限(ターゲットは走る余裕がある層のため上限を設けない)")
    p.add_argument("--top", type=int, default=8)
    args = p.parse_args()

    data = json.load(open(args.src, encoding="utf-8"))
    items = data["items"]
    report = {"総数": len(items)}

    rows, dropped = [], {"ブランド外": 0, "除外語": 0, "価格下限": 0, "価格上限": 0, "レビュー不足": 0, "評価不足": 0}
    for r in items:
        name = clean_name(r["itemName"])
        n = normalize(name)
        brand = detect_brand(r["itemName"])
        if not brand:
            dropped["ブランド外"] += 1; continue
        if any(normalize(k) in n for k in EXCLUDE_KEYWORDS):
            dropped["除外語"] += 1; continue
        if (r["itemPrice"] or 0) < args.min_price:
            dropped["価格下限"] += 1; continue
        if args.max_price is not None and (r["itemPrice"] or 0) > args.max_price:
            dropped["価格上限"] += 1; continue
        if r["reviewCount"] < args.min_reviews:
            dropped["レビュー不足"] += 1; continue
        if r["reviewAverage"] < args.min_average:
            dropped["評価不足"] += 1; continue
        rows.append(dict(r, itemName=name, brand=brand))

    # 同一モデルの重複はレビュー件数が最も多いものを残す
    best = {}
    for r in sorted(rows, key=lambda x: -x["reviewCount"]):
        best.setdefault(model_signature(r["brand"], r["itemName"]), r)
    deduped = sorted(best.values(), key=lambda x: (-x["reviewCount"], -x["reviewAverage"]))
    report["重複除去"] = len(rows) - len(deduped)

    selected = deduped[: args.top]
    payload = dict(
        fetchedAt=data.get("fetchedAt"), source=data.get("source"),
        criteria={"brands": list(BRANDS), "minPrice": args.min_price,
                  "maxPrice": args.max_price, "minReviews": args.min_reviews,
                  "minAverage": args.min_average},
        itemCount=len(selected), items=selected,
    )
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"総数 {report['総数']}件")
    for k, v in dropped.items():
        print(f"  除外 {k}: {v}件")
    print(f"  重複除去: {report['重複除去']}件")
    print(f"\n候補 {len(deduped)}件 → 上位{len(selected)}件を {args.out} に保存\n")
    for r in selected:
        print(f"  ★{r['reviewAverage']:.2f} ({r['reviewCount']:>4}件) {r['itemPrice']:>6}円 "
              f"[{r['taxNote']}/{r['postageNote']}] {r['brand']} | {r['itemName'][:52]}")


if __name__ == "__main__":
    main()
