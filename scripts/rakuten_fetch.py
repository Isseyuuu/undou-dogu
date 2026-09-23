"""楽天市場APIから商品とレビュー集計値を取得する。

このサイトの「独自検証」の代替として、レビュー件数・平均評価の横断集計を使う。
取得できるのは件数と平均であってレビュー本文ではない。本文の傾向は人が読んで
記録する(scripts/review_notes/ を参照)。記事側で両者を混同して書かないこと。

使い方:
    python scripts/rakuten_fetch.py --keyword "ランニングシューズ メンズ" --pages 5
    python scripts/rakuten_fetch.py --genre 208015 --pages 5 --out data/running_shoes.json

認証情報は .env か環境変数から読む(RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY /
RAKUTEN_AFFILIATE_ID)。.env はコミットしないこと。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
JST = timezone(timedelta(hours=9))

# 楽天APIは同一URLへの短時間の連打で応答しなくなる。1req/秒を守る。
REQUEST_INTERVAL_SEC = 1.0
MAX_HITS = 30      # API仕様上の上限
MAX_PAGE = 100     # API仕様上の上限


def load_env(path=".env"):
    """.env を環境変数へ流し込む(既存の環境変数を上書きしない)。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def credentials():
    load_env()
    app_id = os.environ.get("RAKUTEN_APP_ID")
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        sys.exit(
            "RAKUTEN_APP_ID と RAKUTEN_ACCESS_KEY が未設定です。\n"
            "https://webservice.rakuten.co.jp/ でアプリを作成し、.env に次の形式で記載してください:\n"
            "  RAKUTEN_APP_ID=...\n  RAKUTEN_ACCESS_KEY=...\n  RAKUTEN_AFFILIATE_ID=...(任意)"
        )
    return app_id, access_key, os.environ.get("RAKUTEN_AFFILIATE_ID")


def current_global_ip():
    """IP制限で弾かれた際の切り分け用。取得できなくても致命的ではない。"""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as res:
            return res.read().decode("utf-8").strip()
    except Exception as e:
        return f"(取得できませんでした: {e})"


def fetch_page(params, page):
    query = dict(params, page=page)
    url = ENDPOINT + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"User-Agent": "shigoto-dogu/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        if e.code == 429:
            sys.exit(f"429: リクエスト上限に達しました。時間を空けて再実行してください。\n{body}")
        if e.code in (401, 403):
            # アプリ登録時のIP許可リストに現在のIPが無いと拒否される。家庭回線の
            # グローバルIPは固定契約でなければ変わるため、これが最も多い失敗要因。
            # 「キーが失効した」等と誤診しないよう、現在のIPを併記する。
            sys.exit(
                f"HTTP {e.code}: 認証またはIP制限で拒否されました。\n{body}\n"
                f"現在のグローバルIP: {current_global_ip()}\n"
                "楽天ウェブサービスのアプリ設定「許可されたIPアドレス」に"
                "このIPが登録されているか確認してください。"
            )
        sys.exit(f"HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        sys.exit(f"接続に失敗しました: {e.reason}")


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def normalize(item):
    """APIのレスポンスから記事生成に必要な項目だけ取り出す。"""
    return {
        "itemCode": item.get("itemCode"),
        "itemName": strip_tags(item.get("itemName")),
        "shopName": item.get("shopName"),
        "itemPrice": item.get("itemPrice"),
        # taxFlag 0=税込 / 1=税抜。itemPriceは税込とは限らないため、記事側の
        # 税表記はこのフラグで切り替える(決め打ちすると誤表示=景表法リスク)。
        "taxFlag": item.get("taxFlag"),
        "taxNote": "税抜" if item.get("taxFlag") == 1 else "税込",
        "postageFlag": item.get("postageFlag"),
        "postageNote": "送料別" if item.get("postageFlag") == 1 else "送料込",
        "reviewCount": item.get("reviewCount", 0),
        "reviewAverage": float(item.get("reviewAverage") or 0),
        "itemUrl": item.get("itemUrl"),
        "affiliateUrl": item.get("affiliateUrl") or "",
        "imageUrl": (item.get("mediumImageUrls") or [{}])[0].get("imageUrl", ""),
    }


def main():
    p = argparse.ArgumentParser(description="楽天市場APIから商品+レビュー集計を取得")
    p.add_argument("--keyword", help="検索キーワード")
    p.add_argument("--genre", type=int, help="楽天ジャンルID")
    p.add_argument("--pages", type=int, default=3, help=f"取得ページ数 (1ページ{MAX_HITS}件, 最大{MAX_PAGE})")
    p.add_argument("--min-reviews", type=int, default=20, help="この件数未満のレビューは母数不足として除外")
    p.add_argument("--min-price", type=int, help="価格下限(円)")
    p.add_argument("--max-price", type=int, help="価格上限(円)")
    p.add_argument("--sort", default="-reviewCount", help="並び順 (既定: レビュー件数降順)")
    p.add_argument("--out", default="data/rakuten_items.json", help="出力先JSON")
    args = p.parse_args()

    if not args.keyword and not args.genre:
        p.error("--keyword か --genre のどちらかが必要です")
    if not 1 <= args.pages <= MAX_PAGE:
        p.error(f"--pages は 1〜{MAX_PAGE} の範囲で指定してください")

    app_id, access_key, affiliate_id = credentials()

    params = {
        "applicationId": app_id,
        "accessKey": access_key,
        "hits": MAX_HITS,
        "sort": args.sort,
        "format": "json",
    }
    if args.keyword:
        params["keyword"] = args.keyword
    if args.genre:
        params["genreId"] = args.genre
    if args.min_price:
        params["minPrice"] = args.min_price
    if args.max_price:
        params["maxPrice"] = args.max_price
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    items = {}
    for page in range(1, args.pages + 1):
        data = fetch_page(params, page)
        batch = data.get("Items") or []
        if not batch:
            print(f"page {page}: 0件。取得を打ち切ります。")
            break
        for entry in batch:
            row = normalize(entry.get("Item", entry))
            if row["itemCode"]:
                items[row["itemCode"]] = row  # itemCodeで重複排除
        print(f"page {page}: {len(batch)}件取得 (累計ユニーク {len(items)}件)")
        if page < args.pages:
            time.sleep(REQUEST_INTERVAL_SEC)

    rows = [r for r in items.values() if r["reviewCount"] >= args.min_reviews]
    rows.sort(key=lambda r: (-r["reviewCount"], -r["reviewAverage"]))

    if affiliate_id:
        missing = sum(1 for r in rows if not r["affiliateUrl"])
        if missing:
            print(f"注意: affiliateUrlが空の商品が{missing}件あります(提携状態を確認してください)")
    else:
        print("注意: RAKUTEN_AFFILIATE_ID が未設定のため affiliateUrl は空です。")

    payload = {
        "fetchedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "source": "楽天市場 商品検索API (レビュー件数・平均評価は楽天市場の集計値)",
        "query": {
            "keyword": args.keyword, "genreId": args.genre, "sort": args.sort,
            "pages": args.pages, "minReviews": args.min_reviews,
            "minPrice": args.min_price, "maxPrice": args.max_price,
        },
        "itemCount": len(rows),
        "items": rows,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n{len(rows)}件を {args.out} に保存しました(レビュー{args.min_reviews}件以上)。")
    for r in rows[:10]:
        print(f"  ★{r['reviewAverage']:.2f} ({r['reviewCount']:>5}件) {r['itemPrice']:>7}円  {r['itemName'][:42]}")


if __name__ == "__main__":
    main()
