# skk-to-mazedict

tsf-tutcode 向け交ぜ書き変換辞書の自動生成ツール。

SKK-JISYO.L（一般的なSKK辞書）と mazedict.txt（tsf-tutcode 付属辞書）を統合し、
漢直入力に最適化した交ぜ書き辞書を生成します。

## 処理内容

1. **辞書ロード・マージ** — mazedict.txt を優先し、SKK-JISYO.L を統合
2. **送りあり変換** — `わるよi /悪酔/` → `わるよ― /悪酔/`（U+2015）
3. **交ぜ書き展開** — `わめい /和名/` から `和めい /和名/`、`わ名 /和名/` を自動生成
   - KANJIDIC2 の読み候補 + 動的計画法で漢字ごとの読みを特定
   - 如月（きさらぎ）などの熟字訓・当て字は展開しない保守的設計
4. **SKK 形式出力** — UTF-8 の `;; okuri-nasi entries.` 形式

## セットアップ

```bash
uv sync
```

## 使い方

```bash
# 辞書をダウンロードして生成（初回は .cache/ にキャッシュ）
uv run python generate_mazedict.py

# ローカルファイルを使用
uv run python generate_mazedict.py --skk SKK-JISYO.L --mazedict mazedict.txt

# 交ぜ書き展開なし（フェーズ1・2のみ、高速確認用）
uv run python generate_mazedict.py --no-expand

# オプション一覧
uv run python generate_mazedict.py --help
```

## オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `--skk` | （ダウンロード） | SKK-JISYO.L のパス |
| `--mazedict` | （ダウンロード） | mazedict.txt のパス |
| `--output` | `output_mazedict.txt` | 出力ファイル |
| `--max-kanji` | `6` | 展開する漢字数の上限（`2^N-1` エントリ） |
| `--no-expand` | — | 交ぜ書き展開をスキップ |

## 依存ライブラリ

| ライブラリ | 用途 |
|---|---|
| jamdict + jamdict-data | KANJIDIC2 による漢字読み候補取得 |
| jaconv | カタカナ→ひらがな変換 |

## 設計判断

### なぜ `okuri-nasi entries.` 形式のみに統一するか

tsf-tutcode の交ぜ書き変換機能は辞書の `;; okuri-nasi entries.` ブロックのみを検索します。
活用語（動詞・形容詞）を交ぜ書き変換する際は、末尾に `―`（U+2015）を付与したキーで検索する仕様です。

そのため、SKK-JISYO.L の `okuri-ari` エントリ（例：`わるよi /悪酔/`）は
末尾のアルファベットを `―` に置換して `okuri-nasi` エントリとして出力します
（例：`わるよ― /悪酔/`）。

### なぜ 2^N の展開エントリを許容するか

交ぜ書き変換時の辞書検索は tsf-tutcode の設定ツールが辞書をソート済み `skkdict.txt`（UTF-16）に
変換し、ファイルオフセット配列（4 bytes/entry）だけをメモリに保持してバイナリサーチ（O(log N)）
を行います。約 985,000 エントリでも検索ステップ数は約 20 回、メモリ使用量はオフセット配列のみで
約 4 MB です。2^N 展開によるエントリ数増加は検索性能に実質的な影響を与えません。

### 元の辞書の問題と本ツールの解決

- **SKK-JISYO.L 単独**：漢直特有の交ぜ書きエントリ（`和めい /和名/` など）が存在しない
- **mazedict.txt 単独**：収録語彙が限定的（漢直で入力できない字種のフォローアップが主目的）
- **本ツール**：両辞書を統合しつつ、全漢字語について自動的に交ぜ書きエントリを展開

### アライメント（漢字と読みの対応付け）

「和名（わめい）」→ `和=わ, 名=めい` のように各漢字に読みを割り当てることで
`和めい /和名/`、`わ名 /和名/` を自動生成します。
KANJIDIC2（jamdict 経由）から各漢字の読み候補を取得し、動的計画法で
読み文字列を各漢字へ過不足なく割り当てられるか検証します。
「如月（きさらぎ）」のような熟字訓・当て字は分割不能として展開をスキップします。

### 漢字数の上限（`--max-kanji`）

デフォルト上限は 6 文字（63 エントリ/語）です。7 文字以上の全漢字語は SKK-JISYO.L に
約 386 エントリ存在しますが、大半が機関名・略称の長い正式名称です：

| 語 | 読み |
|---|---|
| 国際基督教大学 | こくさいきりすときょうだいがく（ICU）|
| 連合国軍総司令部 | れんごうこくぐんそうしれいぶ（GHQ）|
| 後天性免疫不全症候群 | こうてんせいめんえきふぜんしょうこうぐん（AIDS）|
| 国際連合難民高等弁務官事務所 | （UNHCR）|

これらの語は漢直で一部漢字のみ直接入力して交ぜ書き変換する用途には向かないため、
上限を設けてもほとんど実用上の影響はありません。必要であれば `--max-kanji` で変更できます。

## データ出典

- [SKK-JISYO.L](https://github.com/skk-dev/dict) — GPL
- [tsf-tutcode / mazedict.txt](https://github.com/kanchoku/tsf-tutcode) — 各ライセンス参照
- [KANJIDIC2 / JMdict](https://www.edrdg.org/) — CC BY-SA 4.0

## ライセンス

本ツールおよび生成された辞書は GNU General Public License v2 以降の条件で配布されます。
SKK-JISYO.L（GPL）と mazedict.txt（kwmaze.dic 由来、GPL）を統合するため、
出力辞書は GPL を継承します。詳細は [LICENSE](LICENSE) を参照してください。
