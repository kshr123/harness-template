"""画面から出来事（定例会議など）を足す・直す・消す（`docs/wbs.yaml` の `events`）。

出来事は完了状態を持たない有限個の開催日の集合（`overlay.Event`）。書き戻し先は `docs/wbs.yaml` の
`events:` ブロック**ただ 1 か所**で、他のキー（暦・名簿・節）は 1 バイトも触らない。マイルストーンや作業と
違い、`events` は道具だけが書く構造化リスト（人がコメントを混ぜて手書きするものではない）なので、その
ブロックだけをまるごと書き直す＝差分は `events` の中に限られる。合否の門は UI でなく `Event`/`Overlay` の
読み込み検査（有限性・開催日 1 件以上・ID 一意）＝書く前に組み立て直して通らなければ書かない（fail-closed）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from harness.deliver import history
from harness.deliver.editor import LOCK, EditRejected, _scalar
from harness.deliver.overlay import EVENT_ID_PREFIX, OVERLAY_PATH, Event, Overlay, load_overlay


@dataclass(frozen=True)
class EventInput:
    """画面から来た出来事 1 件（id が空なら新規＝採番する）。"""

    name: str
    lane: str
    id: str = ""
    dtstart: date | None = None
    rrule: str | None = None
    rdate: tuple[date, ...] = ()
    exdate: tuple[date, ...] = ()


def next_event_id(overlay: Overlay) -> str:
    """まだ使っていない出来事の ID（既存の最大＋1・再利用しない）。"""
    used = [int(m.group(1)) for e in overlay.events if (m := re.fullmatch(rf"{EVENT_ID_PREFIX}(\d+)", e.id))]
    return f"{EVENT_ID_PREFIX}{max(used, default=0) + 1:03d}"


def _to_event(inp: EventInput, event_id: str) -> Event:
    """入力を `Event` にする（ここで有限性・開催日 1 件以上などの検査が効く）。"""
    return Event(
        id=event_id,
        name=inp.name,
        lane=inp.lane,
        dtstart=inp.dtstart,
        rrule=inp.rrule,
        rdate=list(inp.rdate),
        exdate=list(inp.exdate),
    )


def _dump_events(events: list[Event]) -> list[str]:
    """`events:` ブロックの本文を組み立てる（空の欄は書かない・人が書いた見た目に寄せる）。"""
    if not events:
        return []
    lines = ["events:"]
    for e in events:
        lines.append(f"  - id: {e.id}")
        lines.append(f"    name: {_scalar(e.name)}")
        lines.append(f"    lane: {_scalar(e.lane)}")
        if e.dtstart is not None:
            lines.append(f"    dtstart: {e.dtstart.isoformat()}")
        if e.rrule is not None:
            lines.append(f'    rrule: "{e.rrule}"')
        if e.rdate:
            lines.append(f"    rdate: [{', '.join(d.isoformat() for d in e.rdate)}]")
        if e.exdate:
            lines.append(f"    exdate: [{', '.join(d.isoformat() for d in e.exdate)}]")
    return lines


def _splice_events(text: str, events: list[Event]) -> str:
    """ファイル本文の `events:` ブロックだけを差し替える（無ければ末尾に足す）。他のキーは触らない。"""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"^events\s*:", ln)), None)
    block = _dump_events(events)
    if start is None:
        head = lines if not lines or lines[-1].strip() == "" else [*lines, ""]
        return "\n".join([*head, *block]).rstrip("\n") + "\n"
    end = len(lines)
    for j in range(start + 1, len(lines)):  # ブロックの終わり＝字下げの無い次のキー
        if lines[j].strip() and not lines[j].startswith((" ", "\t", "#")):
            end = j
            break
    return "\n".join([*lines[:start], *block, *lines[end:]]).rstrip("\n") + "\n"


def _write(root: Path, events: list[Event], today: date) -> None:
    """検査を通してから `events:` を書き戻す（増えた指摘があれば書かない）。"""
    from harness.deliver.wbs_lint import all_problems

    path = root / OVERLAY_PATH
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    new_text = _splice_events(original or "", events)
    try:
        Overlay.model_validate(yaml.safe_load(new_text) or {})  # 有限性・ID 一意などはここで落ちる
    except Exception as exc:  # noqa: BLE001  pydantic/yaml のどちらでも同じ拒否にする
        raise EditRejected(f"出来事として読めない書き方になった: {exc}") from exc
    before = {p.message for p in all_problems(root, today=today) if p.level == "error"}
    path.parent.mkdir(parents=True, exist_ok=True)
    history.record(path)
    path.write_text(new_text, encoding="utf-8")
    introduced = [p for p in all_problems(root, today=today) if p.level == "error" and p.message not in before]
    if introduced:
        if original:
            path.write_text(original, encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        raise EditRejected("　/　".join(p.message for p in introduced))


def upsert_event(root: Path, inp: EventInput, *, today: date) -> str:
    """出来事を足す（id 空）／直す（id 指定）。書いた出来事の ID を返す。"""
    with LOCK:
        overlay = load_overlay(root)
        events = list(overlay.events)
        event_id = inp.id or next_event_id(overlay)
        new_event = _to_event(inp, event_id)
        replaced = False
        for i, e in enumerate(events):
            if e.id == event_id:
                events[i] = new_event
                replaced = True
                break
        if not replaced:
            events.append(new_event)
        _write(root, events, today)
        return event_id


def remove_event(root: Path, event_id: str, *, today: date) -> None:
    """出来事を 1 件消す。"""
    with LOCK:
        overlay = load_overlay(root)
        events = [e for e in overlay.events if e.id != event_id]
        if len(events) == len(overlay.events):
            raise EditRejected(f"出来事 '{event_id}' が {OVERLAY_PATH} に見つからない")
        _write(root, events, today)
