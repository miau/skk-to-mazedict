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

## データ出典

- [SKK-JISYO.L](https://github.com/skk-dev/dict) — GPL
- [tsf-tutcode / mazedict.txt](https://github.com/kanchoku/tsf-tutcode) — 各ライセンス参照
- [KANJIDIC2 / JMdict](https://www.edrdg.org/) — CC BY-SA 4.0
