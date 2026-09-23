"""楽天のジャンルIDを確定させる。

キーワード検索は「ランニングシューズ」で靴紐・インソール・格安スニーカーまで
拾ってしまう(実データで確認済み)。対象カテゴリを正確に絞るにはジャンル指定が要る。
ただしジャンルIDを推測で決めると別カテゴリを集計するため、必ずこのスクリプトで
階層を降りてジャンル名を目視確認してから使うこと。

使い方:
    python scripts/rakuten_genre.py            # ルートから直下を表示
    python scripts/rakuten_genre.py 101070     # 指定ジャンルの直下を表示
    python scripts/rakuten_genre.py 101070 --find シューズ   # 直下を名前で絞り込み

2026年版APIはレスポンス形式が旧版と異なる(children がフラットな配列、名称キーは
nameJa)。旧記事のサンプルコードをそのまま流用しないこと。
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from rakuten_fetch import credentials

ENDPOINT = "https://openapi.rakuten.co.jp/ichibagt/api/IchibaGenre/Search/20260701"


def fetch_genre(genre_id):
    app_id, access_key, _ = credentials()
    params = {
        "applicationId": app_id,
        "accessKey": access_key,
        "genreId": genre_id,
        "format": "json",
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "shigoto-dogu/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}")


def name_of(node):
    return node.get("nameJa") or node.get("genreName") or "(名称不明)"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    genre_id = args[0] if args else "0"
    needle = None
    if "--find" in sys.argv:
        i = sys.argv.index("--find")
        if i + 1 < len(sys.argv):
            needle = sys.argv[i + 1]

    data = fetch_genre(genre_id)

    current = data.get("genre") or {}
    print(f"現在地: {name_of(current) if current else '(ルート)'} (id={current.get('genreId', 0)})")

    ancestors = data.get("ancestors") or []
    if ancestors:
        print("上位: " + " > ".join(name_of(a) for a in ancestors))
    print()

    children = data.get("children") or []
    if not children:
        print("直下のジャンルはありません(末端カテゴリ)。このIDが使えます。")
        return

    if needle:
        children = [c for c in children if needle in name_of(c)]
        if not children:
            print(f"「{needle}」を含む直下ジャンルはありません。")
            return

    print("直下のジャンル:")
    for c in children:
        print(f"  {c.get('genreId'):>10}  {name_of(c)}")
    print("\n目的のジャンル名を確認し、そのIDで再度実行して末端まで降りてください。")


if __name__ == "__main__":
    main()
