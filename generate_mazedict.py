#!/usr/bin/env python3
"""tsf-tutcode 向け交ぜ書き変換辞書生成ツール"""

import re
import sys
import argparse
import urllib.request
from pathlib import Path
from collections import defaultdict

SKK_JISYO_URL = "https://raw.githubusercontent.com/skk-dev/dict/master/SKK-JISYO.L"
MAZEDICT_URL  = "https://raw.githubusercontent.com/kanchoku/tsf-tutcode/master/installer/config-share/mazedict.txt"
OKURI_DASH    = "―"  # ―
MAX_KANJI     = 6

# ─── 文字種判定 ──────────────────────────────────────────────────────────

def is_kanji(ch: str) -> bool:
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or
            0x3400 <= cp <= 0x4DBF or
            0x20000 <= cp <= 0x2A6DF or
            0xF900 <= cp <= 0xFAFF)

def is_hiragana(ch: str) -> bool:
    return "ぁ" <= ch <= "ゖ"

def is_all_kanji(s: str) -> bool:
    return bool(s) and all(is_kanji(c) for c in s)

def is_all_hiragana(s: str) -> bool:
    return bool(s) and all(is_hiragana(c) for c in s)

# ─── SKK辞書パーサー ──────────────────────────────────────────────────────

_LINE_RE = re.compile(r"^(\S+)\s+(/.*/)$")

def _parse_candidates(cand_str: str) -> list[str]:
    return [p for p in cand_str.strip("/").split("/") if p]

def load_skk_dict(text: str) -> tuple[dict, dict]:
    """→ (okuri_ari, okuri_nasi)  各 dict[str, list[str]]"""
    okuri_ari  = defaultdict(list)
    okuri_nasi = defaultdict(list)
    section = None

    for line in text.splitlines():
        s = line.strip()
        if s.startswith(";; okuri-ari"):
            section = "ari"; continue
        if s.startswith(";; okuri-nasi"):
            section = "nasi"; continue
        if not s or s.startswith(";;") or section is None:
            continue
        m = _LINE_RE.match(s)
        if not m:
            continue
        reading = m.group(1)
        # > (接尾辞) / < (接頭辞) マーカーを除去して通常エントリとして扱う
        if reading.startswith(">") or reading.startswith("<"):
            reading = reading[1:]
        if not reading:
            continue
        cands   = _parse_candidates(m.group(2))
        target  = okuri_ari if section == "ari" else okuri_nasi
        for c in cands:
            if c not in target[reading]:
                target[reading].append(c)

    return okuri_ari, okuri_nasi

# ─── 送りあり → ― 変換 ──────────────────────────────────────────────────

def convert_okuri_ari(okuri_ari: dict) -> dict:
    """末尾アルファベット（活用子）を OKURI_DASH に置換してマージ"""
    result = defaultdict(list)
    for reading, cands in okuri_ari.items():
        if reading and reading[-1].isascii() and reading[-1].isalpha():
            key = reading[:-1] + OKURI_DASH
            for c in cands:
                if c not in result[key]:
                    result[key].append(c)
    return result

# ─── 辞書マージ ──────────────────────────────────────────────────────────

def merge_dicts(*dicts) -> dict:
    """先に登録された候補を優先してマージ"""
    result = defaultdict(list)
    for d in dicts:
        for reading, cands in d.items():
            for c in cands:
                if c not in result[reading]:
                    result[reading].append(c)
    return result

# ─── KANJIDIC2 読み取得 ──────────────────────────────────────────────────

# 五段動詞の終止形末尾 → 連用形末尾（す→し、う→い 等）
_U_TO_I = str.maketrans('うくぐすつぬぶむる', 'いきぎしちにびみり')

def _renyou_forms(stem: str, okuri: str) -> list[str]:
    """
    訓読み「ほ.す」「あ.う」「う.ける」から連用形の読みを作る。
    例: ほ.す→['ほし']  あ.う→['あい']  う.ける→['うけ', 'うけり']
    る で終わる語は五段（と.る→とり）か一段（う.ける→うけ）か区別できないため両方返す。
    形容詞（〜い）などの u 段以外で終わる送り仮名は対象外。
    """
    if not okuri or okuri[-1] not in 'うくぐすつぬぶむる':
        return []
    forms = [stem + okuri[:-1] + okuri[-1].translate(_U_TO_I)]
    if okuri[-1] == 'る' and len(okuri) >= 2:
        forms.insert(0, stem + okuri[:-1])  # 一段動詞
    return forms

class KanjiReadings:
    """KANJIDIC2（jamdict 経由）から漢字ごとの読み候補を返すキャッシュ付きクラス"""

    def __init__(self) -> None:
        self._cache: dict[str, list[str]] = {}
        self._ext_cache: dict[str, list[str]] = {}
        self._jam = None

    def _init(self) -> bool:
        if self._jam is not None:
            return True
        try:
            from jamdict import Jamdict
            self._jam = Jamdict()
            return True
        except Exception as e:
            print(f"[警告] jamdict 初期化失敗: {e}", file=sys.stderr)
            return False

    def get(self, kanji: str) -> list[str]:
        if kanji in self._cache:
            return self._cache[kanji]
        readings: list[str] = []
        if self._init():
            try:
                import jaconv
                result = self._jam.lookup(kanji)
                for ch in result.chars:
                    for rmg in ch.rm_groups:
                        for r in rmg.readings:
                            if r.r_type not in ("ja_on", "ja_kun", "nanori"):
                                continue
                            # 訓読みの送り仮名部分（.以降）を除去してひらがなに統一
                            hira = jaconv.kata2hira(r.value.split(".")[0])
                            if hira and hira not in readings:
                                readings.append(hira)
            except Exception:
                pass
        self._cache[kanji] = readings
        return readings

    def get_extended(self, kanji: str) -> list[str]:
        """
        get() の読みに、連用形（干=ほし、合=あい）と接辞マーカー（-）を外した読みを追加。
        get() だけでは「場合（ばあい）」「干場（ほしば）」のような連用形を含む語が分割できない。
        """
        if kanji in self._ext_cache:
            return self._ext_cache[kanji]
        readings = list(self.get(kanji))
        extra: list[str] = []
        if self._init():
            try:
                import jaconv
                result = self._jam.lookup(kanji)
                for ch in result.chars:
                    for rmg in ch.rm_groups:
                        for r in rmg.readings:
                            if r.r_type not in ("ja_on", "ja_kun", "nanori"):
                                continue
                            hira = jaconv.kata2hira(r.value).strip("-")
                            stem, _, okuri = hira.partition(".")
                            extra.append(stem)
                            if r.r_type == "ja_kun":
                                extra.extend(_renyou_forms(stem, okuri))
            except Exception:
                pass
        for e in extra:
            if e and e not in readings:
                readings.append(e)
        self._ext_cache[kanji] = readings
        return readings

# ─── 連濁テーブル ────────────────────────────────────────────────────────

# 先頭1文字の連濁（有声→無声）を解除するための変換テーブル
_RENDAKU = str.maketrans(
    'がぎぐげござじずぜぞだぢづでどばびぶべぼ',
    'かきくけこさしすせそたちつてとはひふへほ',
)

def _devoice(s: str) -> str:
    """先頭1文字のみ連濁を解除（がみ→かみ等）"""
    return s[0].translate(_RENDAKU) + s[1:] if s else s

# 促音・撥音の後の半濁音（ぽん→ほん）を解除するための変換テーブル
_HANDAKU = str.maketrans('ぱぴぷぺぽ', 'はひふへほ')

def _unhandaku(s: str) -> str:
    """先頭1文字のみ半濁音を解除（ぽん→ほん等）"""
    return s[0].translate(_HANDAKU) + s[1:] if s else s

# 促音便になりうる読みの末尾（がく→がっ、いち→いっ、ひき→ひっ、とり→とっ）
_SOKUON_TAILS = 'くきちつり'

def _seg_matches(seg: str, r: str, prev: str, extended: bool) -> bool:
    """
    読みの一部 seg が漢字の読み候補 r に一致するか。
    基本: 完全一致、または先頭1文字の連濁を解除して一致。
    extended: 直前が っ/ん のときの半濁音（切符 きっ+ぷ、散歩 さん+ぽ）と、
              末尾の促音便（学校 がっ+こう、取手 とっ+て）も許容。
    """
    if seg == r or _devoice(seg) == r:
        return True
    if not extended:
        return False
    heads = {seg, _devoice(seg)}
    if prev and prev[-1] in 'っん':
        heads.add(_unhandaku(seg))
    if r in heads:
        return True
    if len(r) >= 2 and r[-1] in _SOKUON_TAILS and seg[-1] == 'っ':
        return any(h[:-1] == r[:-1] for h in heads)
    return False

# ─── DP アライメント ─────────────────────────────────────────────────────

def align(word: str, reading: str, kdb: KanjiReadings) -> list[str] | None:
    """
    KANJIDIC2 の読み候補 + 動的計画法で word の各文字に reading を割り当てる。
    - 漢字: KANJIDIC2 の読み候補（連濁形も許容）
    - ひらがな: 自身と完全一致のみ
    基本の読みで失敗した場合のみ、連用形などの拡張読み・促音便・半濁音で再試行する
    （既存のアライメント結果を変えないため）。
    成功: ['わ', 'めい']  失敗（熟字訓等）: None
    """
    return (_align(word, reading, kdb.get, False)
            or _align(word, reading, kdb.get_extended, True))

def _align(word: str, reading: str, get_readings, extended: bool) -> list[str] | None:
    n, m = len(word), len(reading)
    # ひらがなは自身のみ、漢字は KANJIDIC2 から取得
    cands = [[ch] if is_hiragana(ch) else get_readings(ch) for ch in word]

    def search(ki: int, ri: int, prev: str) -> list[str] | None:
        if ki == n:
            return [] if ri == m else None
        for r in cands[ki]:
            end = ri + len(r)
            seg = reading[ri:end]
            if len(seg) == len(r) and _seg_matches(seg, r, prev, extended):
                rest = search(ki + 1, end, seg)
                if rest is not None:
                    return [seg] + rest  # 連濁形・促音便形のまま記録
        return None

    return search(0, 0, "")

# ─── 交ぜ書き展開 ────────────────────────────────────────────────────────

def expand_mazekai(word: str, alignment: list[str]) -> list[str]:
    """
    漢字位置のみを漢字/かな交互に切り替えた交ぜ書きキーを返す（全かな・全漢字を除く）。
    例: word='和名', alignment=['わ','めい'] → ['和めい', 'わ名']
    例: word='痛み止め', alignment=['いた','み','ど','め'] → ['痛みどめ', 'いたみ止め']
    漢字が1文字以下の場合は空リストを返す。
    """
    kanji_pos = [i for i in range(len(word)) if is_kanji(word[i])]
    nk = len(kanji_pos)
    if nk < 2:
        return []
    all_kanji_mask = (1 << nk) - 1
    keys = []
    for mask in range(1, all_kanji_mask):  # 全かな(0)・全漢字(all_kanji_mask) を除く
        parts = list(word)
        for ki, pos in enumerate(kanji_pos):
            if not (mask >> ki) & 1:
                parts[pos] = alignment[pos]  # 漢字をその読みで置換
        keys.append("".join(parts))
    return keys

# ─── ファイル取得 ─────────────────────────────────────────────────────────

def _decode_auto(data: bytes, fallback: str) -> str:
    """UTF-16 BOM → utf-16、UTF-8 として有効 → utf-8、それ以外 → fallback"""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(fallback, errors="replace")

def fetch(url: str, cache: Path, encoding: str) -> str:
    if cache.exists():
        print(f"  キャッシュ使用: {cache}", file=sys.stderr)
        return cache.read_text(encoding="utf-8", errors="replace")
    print(f"  ダウンロード: {url}", file=sys.stderr)
    with urllib.request.urlopen(url) as r:
        data = r.read()
    text = _decode_auto(data, encoding)
    cache.write_text(text, encoding="utf-8")
    return text

def read_local(path: Path, fallback: str) -> str:
    """ローカルファイルをエンコーディング自動検出で読む（UTF-16/UTF-8/fallback）"""
    return _decode_auto(path.read_bytes(), fallback)

# ─── メイン ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="tsf-tutcode 向け交ぜ書き辞書生成")
    ap.add_argument("--skk",       default=None,                  help="SKK-JISYO.L のパス（省略時はダウンロード）")
    ap.add_argument("--mazedict",  default=None,                  help="mazedict.txt のパス（省略時はダウンロード）")
    ap.add_argument("--output",    default="output_mazedict.txt", help="出力ファイル")
    ap.add_argument("--max-kanji", type=int, default=MAX_KANJI,   help="展開する漢字数の上限（既定: 6）")
    ap.add_argument("--no-expand", action="store_true",           help="交ぜ書き展開をスキップ")
    args = ap.parse_args()

    log = lambda *a: print(*a, file=sys.stderr)
    cache = Path(".cache")
    cache.mkdir(exist_ok=True)

    # ── 辞書ロード ──────────────────────────────────────────────────────
    log("=== 辞書ロード ===")
    skk_text  = (read_local(Path(args.skk), "euc-jp")
                 if args.skk else fetch(SKK_JISYO_URL, cache / "SKK-JISYO.L", "euc-jp"))
    maze_text = (read_local(Path(args.mazedict), "utf-8")
                 if args.mazedict else fetch(MAZEDICT_URL, cache / "mazedict.txt", "utf-8"))

    log("SKK-JISYO.L パース中…")
    skk_ari, skk_nasi = load_skk_dict(skk_text)
    log(f"  okuri-ari: {len(skk_ari):,}  okuri-nasi: {len(skk_nasi):,}")

    log("mazedict.txt パース中…")
    _, maze_nasi = load_skk_dict(maze_text)
    log(f"  okuri-nasi: {len(maze_nasi):,}")

    # ── 送りあり → ― ────────────────────────────────────────────────────
    log("=== 送りあり → ― 変換 ===")
    conv = convert_okuri_ari(skk_ari)
    log(f"  変換後: {len(conv):,} エントリ")

    # ── マージ（mazedict 優先）──────────────────────────────────────────
    log("=== マージ ===")
    merged = merge_dicts(maze_nasi, skk_nasi, conv)
    log(f"  マージ後: {len(merged):,} エントリ")

    # ── 交ぜ書き展開 ─────────────────────────────────────────────────────
    if not args.no_expand:
        log("=== 交ぜ書き展開 ===")
        kdb = KanjiReadings()
        ok = skip_jukuji = skip_long = 0
        new_entries: dict[str, list[str]] = defaultdict(list)

        items = list(merged.items())
        for idx, (reading, cands) in enumerate(items):
            if idx % 20000 == 0:
                log(f"  {idx:,}/{len(items):,}…")

            # 送りあり由来のキー（わるよ―）は展開後のキーにも ― を付ける（わる酔―、悪よ―）
            suffix = OKURI_DASH if reading.endswith(OKURI_DASH) else ""
            base = reading[:-1] if suffix else reading
            if not is_all_hiragana(base):
                continue

            for word in cands:
                word = word.split(";")[0]  # アノテーション（;注釈）を除去
                nk = sum(1 for c in word if is_kanji(c))
                if nk < 2:  # 漢字が2文字未満は展開不要
                    continue
                if nk > args.max_kanji:
                    skip_long += 1
                    continue

                alignment = align(word, base, kdb)
                if alignment is None:
                    skip_jukuji += 1
                    continue

                for key in expand_mazekai(word, alignment):
                    key += suffix
                    if word not in new_entries[key]:
                        new_entries[key].append(word)
                ok += 1

        log(f"  展開成功: {ok:,}  熟字訓スキップ: {skip_jukuji:,}  文字数超過: {skip_long:,}")

        for key, words in new_entries.items():
            for w in words:
                if w not in merged[key]:
                    merged[key].append(w)
        log(f"  展開後 総エントリ数: {len(merged):,}")

    # ── 出力 ─────────────────────────────────────────────────────────────
    log(f"=== 出力: {args.output} ===")
    out = Path(args.output)
    with out.open("w", encoding="utf-8") as f:
        f.write(";; -*- coding: utf-8 -*-\n")
        f.write(";; tsf-tutcode 向け交ぜ書き変換辞書（skk-to-mazedict 生成）\n")
        f.write(";;\n")
        f.write(";; okuri-nasi entries.\n")
        for reading in sorted(merged):
            cands = merged[reading]
            if cands:
                f.write(f"{reading} /{'/'.join(cands)}/\n")
    log(f"完了: {out.resolve()}")


if __name__ == "__main__":
    main()
