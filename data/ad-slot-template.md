# 楽天広告枠 挿入テンプレート仕様（ランニングシューズ他）

## 目的
`scripts/rakuten_fetch.py` の `normalize()` が出力する商品データを、記事内の
広告枠HTMLへ差し込むための共通仕様。**affiliateUrl が実在するまで、この枠は
記事上でHTMLコメントのまま非公開にする。** ダミーの `href="#"` を公開状態で
置かない（クリックしても何も起きないUIは読者の信用を損なうため）。

## 対象記事と現在の状態
- `articles/running-beginner-gear.html`：2026年8月22日取得データから2商品を公開済み
- `articles/hyrox-beginner-guide.html`：2026年8月22日取得データから1商品を公開済み
- `articles/pickleball-beginner-gear.html`：2026年8月22日取得データから2商品を公開済み

新規記事で未公開枠を用意する場合は、`<!-- RAKUTEN_AD_SLOT: ... --> ... <!-- /RAKUTEN_AD_SLOT -->`
のコメントブロックとして仕込む。中身は下記スケルトンと同一。

## 公開作業の手順
1. `scripts/rakuten_fetch.py` を実行し、`data/rakuten_items.json` を得る
   （`RAKUTEN_AFFILIATE_ID` 未設定時は `affiliateUrl` が空になるため、
   その状態では絶対に公開しない）。
2. `data/review-notes/<商品スラッグ>.md` のレビュー精読メモがあれば併せて参照。
3. 各記事のコメントブロック内、`{{ITEM_n_...}}` を実データで置換する
   （n=1,2。商品は原則2点、レビュー件数上位を採用）。
4. `<!-- RAKUTEN_AD_SLOT: ... -->` と `<!-- /RAKUTEN_AD_SLOT -->` の
   コメント境界を削除し、中身のHTMLだけを残す。
5. `affiliateUrl` が空文字の商品は掲載しない（1点しか埋まらない場合は
   `.ad-options` を1カード構成に変更してよい）。

## プレースホルダーとキー対応（normalize()の出力キーと一致させること）
| プレースホルダー | 由来キー | 備考 |
|---|---|---|
| `{{ITEM_n_NAME}}` | `itemName` | タグ除去済みの商品名 |
| `{{ITEM_n_PRICE}}` | `itemPrice` | 数値（円）。カンマ区切り表示に整形して良い |
| `{{ITEM_n_TAX_NOTE}}` | `taxNote` | 「税込」/「税抜」。**itemPriceは税込とは限らない**(taxFlag 0=税込/1=税抜)。決め打ち禁止 |
| `{{ITEM_n_POSTAGE_NOTE}}` | `postageNote` | 「送料込」/「送料別」(postageFlag 0/1) |
| `{{ITEM_n_REVIEW_COUNT}}` | `reviewCount` | 楽天市場の集計値 |
| `{{ITEM_n_REVIEW_AVERAGE}}` | `reviewAverage` | 小数1桁で表示 |
| `{{ITEM_n_AFFILIATE_URL}}` | `affiliateUrl` | 空なら掲載しない |
| `{{ITEM_n_IMAGE_URL}}` | `imageUrl` | alt文言は商品名を使う |

## 必須要件
- 広告であることの明示ラベル（`<p class="tag">広告</p>`）を含める。
- 広告リンクの `<a>` には `rel="sponsored nofollow"` を必ず付与する。
- レビュー件数・平均評価には「楽天市場の集計値」であり当サイトの実測では
  ないことを明記する（景表法・ステマ規制対策。CLAUDE.md/このリポジトリの
  方針と同じ考え方）。
- 既存記事の `.cta`/`.ad-options`/`.ad-card`
  と同じCSSクラスを使い、見た目のトーンを揃える。

## HTMLスケルトン（記事側に仕込んでいるものと同一）
```html
<div class="cta" id="shoes-picks">
  <p class="tag">広告</p>
  <h2>レビューが多いランニングシューズ（楽天市場）</h2>
  <p class="source-note">価格・在庫は変動します。レビュー件数・平均評価は<strong>楽天市場の集計値</strong>であり、当サイトが実測したものではありません。</p>
  <div class="ad-options">
    <div class="ad-card">
      <strong>{{ITEM_1_NAME}}</strong>
      <img src="{{ITEM_1_IMAGE_URL}}" alt="{{ITEM_1_NAME}}" width="200" height="200" loading="lazy" decoding="async">
      <small>楽天市場価格の目安：{{ITEM_1_PRICE}}円（{{ITEM_1_TAX_NOTE}}・{{ITEM_1_POSTAGE_NOTE}}・変動あり）</small>
      <small>楽天市場のレビュー：★{{ITEM_1_REVIEW_AVERAGE}}（{{ITEM_1_REVIEW_COUNT}}件、楽天市場の集計値）</small>
      <a href="{{ITEM_1_AFFILIATE_URL}}" rel="sponsored nofollow">楽天市場で見る</a>
    </div>
    <div class="ad-card">
      <strong>{{ITEM_2_NAME}}</strong>
      <img src="{{ITEM_2_IMAGE_URL}}" alt="{{ITEM_2_NAME}}" width="200" height="200" loading="lazy" decoding="async">
      <small>楽天市場価格の目安：{{ITEM_2_PRICE}}円（{{ITEM_2_TAX_NOTE}}・{{ITEM_2_POSTAGE_NOTE}}・変動あり）</small>
      <small>楽天市場のレビュー：★{{ITEM_2_REVIEW_AVERAGE}}（{{ITEM_2_REVIEW_COUNT}}件、楽天市場の集計値）</small>
      <a href="{{ITEM_2_AFFILIATE_URL}}" rel="sponsored nofollow">楽天市場で見る</a>
    </div>
  </div>
</div>
```

## 公開前チェック（Claude Codeの裏取り対象）
- `affiliateUrl` が実在し、楽天のアフィリエイトリンクとして機能するか
  （オーナーのアカウント作成完了・提携審査通過が前提）。
- 商品ページの内容（サイズ展開・在庫状況）が記事本文の主張と矛盾しないか。
- 画像URLが楽天CDNの正規URLであること（記事側で改変しない）。
