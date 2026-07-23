"""編集した内容を正本へ書き戻す（行置換・競合検出・書き戻し後の検査）。

**書き込み先は正本ひとつ**（画面の側に状態を溜めない）。作業単位の値は `work/` の frontmatter へ、
手動行の値は `docs/wbs.yaml` へ。どちらも**そのキーの行だけを置き換える**（設定ファイルの `profiles = [...]`
1 行だけを書き換える既存の作法と同じ）＝ファイル全体を書き出し直さないので、コメント・並び・引用符が
そのまま残り、差分は 1 か所あたり数行に収まる。差分だけを見る独立レビューが成り立つ状態を壊さない。

安全のために 3 つ重ねる：

1. **競合検出**：読んだ時点のファイルの指紋を保存時に突き合わせ、違えば書かずに拒否する（別の手＝エディタ・
   エージェント・git の操作で正本が動いていたのに、画面が持っている古い値で上書きするのを止める）。
   読み取りから書き込みまでを 1 つの錠で囲む（同時に 2 つ来たとき、両方が突き合わせを通過して片方が
   黙って消えるのを防ぐ）。
2. **書く前の型検査**：新しい本文を組み立てた時点で pydantic に通し、通らなければ書かない。
3. **書いた後の不変条件の検査**：`wbs_lint` に失敗したら元の中身へ戻して指摘を返す（親子の日程の食い違い・
   依存と日程の矛盾を、画面からの操作で作れないようにする）。
"""

from __future__ import annotations

import hashlib
import re
import threading
from datetime import date
from pathlib import Path

import frontmatter
import yaml
from pydantic import ValidationError

from harness import pm
from harness.deliver.overlay import OVERLAY_PATH, Overlay
from harness.models import Item, Status

# 画面から直せる欄。ここに無いものは編集の対象にしない（導出値には元から欄が無い）。
EDITABLE_WORK_FIELDS: frozenset[str] = frozenset({"title", "status", "owner", "start", "due", "effort_days"})
EDITABLE_MANUAL_FIELDS: frozenset[str] = frozenset({"name", "status", "team", "start", "due", "effort_days"})

# 読み取り〜書き込みを囲う錠（1 人用の道具なので 1 つで足りる）。
_LOCK = threading.Lock()


class EditRejected(Exception):
    """保存を拒否した（競合・型不正・検査失敗）。理由はそのまま画面に出す。"""


def file_digest(path: Path) -> str:
    """ファイルの指紋（無ければ空文字）。画面が読んだ時点の状態を表す。"""
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# YAML が真偽・空として読んでしまう語（この語をそのまま書くと文字列でなくなるので必ず引用符で囲む）。
_YAML_WORDS = frozenset({"y", "n", "yes", "no", "on", "off", "true", "false", "null", "~"})
# 引用符が要る記号（先頭に来ると別の意味になるもの・途中にあると区切りに見えるもの）。
_YAML_SPECIALS = set(":#,[]{}&*!|>'\"%@`")


def _scalar(value: str) -> str:
    """画面から来た文字列を YAML の値の書き方に直す（空は「キーごと消す」を意味する）。

    引用符は**必要なときだけ**付ける。常に囲むと、人が手で書いた行との見た目が変わって差分が読みにくくなる
    （書き戻しても差分が小さいまま、という性質を保つ）。
    """
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) or re.fullmatch(r"-?\d+(\.\d+)?", text):
        return text
    plain = (
        text
        and text.lower() not in _YAML_WORDS
        and not (_YAML_SPECIALS & set(text))
        and text[0] not in "-?"
        and text == text.strip()
    )
    if plain:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _replace_in_block(lines: list[str], start: int, end: int, key: str, value: str | None, indent: str) -> list[str]:
    """lines[start:end] の中の `key:` の行を置き換える（value が None ならその行を消す・無ければ足す）。

    行の頭の空白まで含めて一致を見る＝入れ子の中の同名キーに当たらない。
    """
    pattern = re.compile(rf"^{re.escape(indent)}{re.escape(key)}\s*:.*$")
    for i in range(start, end):
        if pattern.match(lines[i]):
            if value is None:
                return lines[:i] + lines[i + 1 :]
            return lines[:i] + [f"{indent}{key}: {value}"] + lines[i + 1 :]
    if value is None:
        return lines
    return lines[:end] + [f"{indent}{key}: {value}"] + lines[end:]


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int]:
    """frontmatter の中身の範囲（開始の `---` の次の行から、閉じの `---` の行まで）。"""
    if not lines or lines[0].strip() != "---":
        raise EditRejected("frontmatter が見つからない（先頭が --- で始まっていない）")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 1, i
    raise EditRejected("frontmatter が閉じていない")


def _row_bounds(lines: list[str], row_id: str) -> tuple[int, int, str]:
    """手動行 `- id: <row_id>` の塊の範囲と、その中のキーの字下げを返す。"""
    head = re.compile(rf"^(\s*)-\s+id:\s*[\"']?{re.escape(row_id)}[\"']?\s*$")
    for i, line in enumerate(lines):
        match = head.match(line)
        if match is None:
            continue
        dash_indent = match.group(1)
        key_indent = dash_indent + "  "
        end = len(lines)
        for j in range(i + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped and not lines[j].startswith(key_indent):
                end = j
                break
        return i + 1, end, key_indent
    raise EditRejected(f"手動行 '{row_id}' が {OVERLAY_PATH} に見つからない")


def _validated_item_text(text: str) -> None:
    """書く前に、その本文が作業単位として読めるかを確かめる（読めなければ書かない）。"""
    try:
        Item.model_validate(dict(frontmatter.loads(text).metadata))
    except ValidationError as exc:
        raise EditRejected(f"作業単位として読めない値: {exc.error_count()} 件") from exc
    except yaml.YAMLError as exc:
        raise EditRejected(f"frontmatter が壊れる書き方になっている: {exc}") from exc


def _validated_overlay_text(text: str) -> None:
    """書く前に、その本文が上書きとして読めるかを確かめる。"""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EditRejected(f"{OVERLAY_PATH} が壊れる書き方になっている: {exc}") from exc
    try:
        Overlay.model_validate(raw if isinstance(raw, dict) else {})
    except ValidationError as exc:
        raise EditRejected(f"上書きとして読めない値: {exc.error_count()} 件") from exc


def _find_item_path(root: Path, item_id: str) -> Path:
    """作業単位 ID からその単位のファイルを引く。"""
    nodes, _ = pm.load_tree(root)
    for node in _walk(nodes):
        if node.item.id == item_id:
            return node.path / pm.MARKER if node.path.is_dir() else node.path
    raise EditRejected(f"作業単位 '{item_id}' が work/ に見つからない")


def _walk(nodes: list[pm.Node]) -> list[pm.Node]:
    out: list[pm.Node] = []
    for node in nodes:
        out.append(node)
        out.extend(_walk(node.children))
    return out


def _check_field(field: str, allowed: frozenset[str]) -> None:
    if field not in allowed:
        raise EditRejected(f"'{field}' はこの行で直せる欄ではない（直せるのは {sorted(allowed)}）")


def _check_value(field: str, value: str) -> str | None:
    """画面から来た値を確かめて YAML の書き方に直す（空文字はその欄を消すことを意味する）。"""
    text = value.strip()
    if not text:
        return None
    if field in {"start", "due"}:
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise EditRejected(f"日付は YYYY-MM-DD で書く（受け取った値: {text}）") from exc
    if field == "status" and text not in {s.value for s in Status}:
        raise EditRejected(f"状態は {sorted(s.value for s in Status)} のいずれか（受け取った値: {text}）")
    if field == "effort_days":
        try:
            if float(text) <= 0:
                raise EditRejected(f"見積り工数は正の数で書く（受け取った値: {text}）")
        except ValueError as exc:
            raise EditRejected(f"見積り工数は数で書く（受け取った値: {text}）") from exc
    return _scalar(text)


def apply_edit(root: Path, *, ref: str, field: str, value: str, base_digest: str, today: date) -> str:
    """1 か所を直して正本へ書き戻し、書き戻したファイルの新しい指紋を返す。

    `base_digest` は画面がその行を読んだ時点のファイルの指紋。現在と違えば書かずに拒否する。
    成功時に新しい指紋を返すのは、続けて 2 回目を保存するときに古い指紋で誤って拒否されないため。
    """
    from harness.deliver import wbs_lint  # 検査は書いた後に呼ぶだけ（相互 import を避けて局所に置く）

    with _LOCK:
        manual = ref.startswith("W-")
        if manual:
            _check_field(field, EDITABLE_MANUAL_FIELDS)
            path = root / OVERLAY_PATH
        else:
            _check_field(field, EDITABLE_WORK_FIELDS)
            path = _find_item_path(root, ref)

        current = file_digest(path)
        if base_digest and base_digest != current:
            raise EditRejected(
                "画面を開いた後に正本が別の手で書き換わっている（上書きしなかった）。読み込み直してからやり直す"
            )

        original = path.read_text(encoding="utf-8")
        rendered = _check_value(field, value)
        lines = original.splitlines()
        if manual:
            start, end, indent = _row_bounds(lines, ref)
            new_lines = _replace_in_block(lines, start, end, field, rendered, indent)
        else:
            start, end = _frontmatter_bounds(lines)
            new_lines = _replace_in_block(lines, start, end, field, rendered, "")
        new_text = "\n".join(new_lines) + ("\n" if original.endswith("\n") else "")

        if manual:
            _validated_overlay_text(new_text)
        else:
            _validated_item_text(new_text)

        path.write_text(new_text, encoding="utf-8")
        errors = [p for p in wbs_lint.check(root, today=today) if p.level == "error"]
        if errors:
            path.write_text(original, encoding="utf-8")  # 検査に落ちる状態を正本に残さない
            raise EditRejected("　/　".join(p.message for p in errors))
        return file_digest(path)
