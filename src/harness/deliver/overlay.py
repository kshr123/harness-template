"""案件固有の上書き（`docs/wbs.yaml`）のスキーマ。**日程の正本ではない**。

ここに載るのは、作業単位（`work/`）に属さない情報**だけ**：

- `calendar` … 営業日の暦（国・案件の非稼働日・振替出勤）。
- `teams`・`members` … 案件の名簿（画面で選ぶ先）。
- `sections` … 顧客向けの節の構成と表示順（顧客の言葉とエンジニアリング上の構造がずれる場合の翻訳層）。
- `rows` … `work/` に置けない手動行（クライアントの承認待ち・定例会議・先方の作業など）。これらを `work/` に
  置くと `status --next` の着手候補を汚し、done に検証の場所（`verified_by`）を要求する検査と衝突するため、
  木の外に置く。

**導出できる値の欄をここに作らない**：WBS 番号・営業日数・進捗率・親の日程・`work/` を指す項目の状態や実績日は
フィールドとして存在しない（`extra="forbid"` が未知キーも拒否する）＝同じ事実が 2 か所に書ける状態が
構造的に生まれない（保証 (a)）。手動行だけは導出元が無いので `status` を**必須**にする（書かなければ既定で
合格、にしない）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from harness.deliver.calendar import WorkCalendar
from harness.models import Status

OVERLAY_PATH = "docs/wbs.yaml"

# 手動行の ID。`work/` の単位 ID（EP-/T-/E-/INV-）と衝突しない接頭辞にする。
MANUAL_ID_PREFIX = "W-"


class CalendarSpec(BaseModel):
    """営業日の暦の宣言。書かなければ土日だけを非稼働日にする（祝日を見ない）。"""

    model_config = ConfigDict(extra="forbid")

    country: str | None = None  # holidays の国コード（例 "JP"）。None なら祝日を見ない。
    extra_holidays: list[date] = Field(default_factory=list)  # 会社・クライアントの休業日
    extra_workdays: list[date] = Field(default_factory=list)  # 振替出勤（非稼働日の判定を打ち消す）

    def to_calendar(self) -> WorkCalendar:
        """判定に使う暦へ変換する。"""
        return WorkCalendar(
            country=self.country,
            extra_holidays=frozenset(self.extra_holidays),
            extra_workdays=frozenset(self.extra_workdays),
        )


class ManualRow(BaseModel):
    """`work/` に置けない行（クライアント承認待ち・定例会議・先方の作業）。

    導出元（作業単位）が無いので、状態と実績日はここに**保存する**（唯一の置き場になるので二重台帳にならない）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str  # W-001 形式。一意・再利用しない。
    name: str
    team: str | None = None
    assignees: list[str] = Field(default_factory=list)
    start: date | None = None
    due: date | None = None
    effort_days: float | None = Field(default=None, gt=0)
    milestone: bool = False
    depends_on: list[str] = Field(default_factory=list)  # 先行する行・作業単位の ID
    status: Status  # 導出元が無いので必須（無記入を既定で合格にしない）
    actual_start: date | None = None
    actual_finish: date | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check(self) -> ManualRow:
        """手動行の中で閉じる矛盾を、読み込んだ時点で落とす（保証 (a)）。"""
        if not self.id.startswith(MANUAL_ID_PREFIX):
            raise ValueError(
                f"手動行の id '{self.id}' は '{MANUAL_ID_PREFIX}' で始めること（作業単位の ID と混ざらないように）"
            )
        if self.milestone:
            if self.due is None:
                raise ValueError(f"{self.id}: milestone には due（マイルストーンの日）が要る")
            if self.start is not None:
                raise ValueError(f"{self.id}: マイルストーンは期間ゼロの点なので start を持たない")
        if self.start is not None and self.due is not None and self.start > self.due:
            raise ValueError(f"{self.id}: start が due より後になっている")
        if self.actual_start is not None and self.actual_finish is not None and self.actual_start > self.actual_finish:
            raise ValueError(f"{self.id}: actual_start が actual_finish より後になっている")
        if self.actual_finish is not None and self.status is not Status.done:
            raise ValueError(f"{self.id}: actual_finish があるのに status が done でない")
        return self


class SectionEntry(BaseModel):
    """節に並べる 1 項目。`work`（作業単位を指す）か `row`（手動行を指す）のどちらか一方。"""

    model_config = ConfigDict(extra="forbid")

    work: str | None = None  # 作業単位の ID（例 EP-90）。日程・状態はそこから導出する。
    row: str | None = None  # 手動行の ID（例 W-001）

    @model_validator(mode="after")
    def _exactly_one(self) -> SectionEntry:
        """work と row はどちらか一方だけ（両方・どちらも無しは読み込み時に落とす）。"""
        if (self.work is None) == (self.row is None):
            raise ValueError("節の項目は work（作業単位 ID）か row（手動行 ID）のどちらか一方を書く")
        return self


class Section(BaseModel):
    """顧客向けの節（フェーズ）。中身は作業単位への参照と手動行の並び。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    team: str | None = None
    entries: list[SectionEntry] = Field(default_factory=list)


class Overlay(BaseModel):
    """`docs/wbs.yaml` 全体。ファイルが無ければすべて既定（節構成は木からそのまま導く）。"""

    model_config = ConfigDict(extra="forbid")

    project: str | None = None  # 表紙に出す案件名。無ければ出さない。
    client: str | None = None  # 提出先（クライアント名）。無ければ出さない。
    calendar: CalendarSpec = Field(default_factory=CalendarSpec)
    sections: list[Section] = Field(default_factory=list)
    rows: list[ManualRow] = Field(default_factory=list)
    # 顧客向けの WBS に**載せない**作業単位の ID（社内都合の作業など）。節構成が木を覆っていない単位は
    # 既定で検査に失敗する（黙って消えるのを止める）ので、外すなら差分に残る形でここに明示する。
    exclude: list[str] = Field(default_factory=list)
    # 案件の名簿。画面ではここから選ぶ（毎回打つと表記ゆれが起きる＝同じ人が別人として集計される）。
    # 画面で新しい名前を入れると、ここにも足される（選ぶ先と実際に使われている名前がずれない）。
    teams: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_row_ids(self) -> Overlay:
        """手動行の ID の重複は読み込み時に落とす（参照先が一意に決まらなくなるため）。"""
        seen: set[str] = set()
        for row in self.rows:
            if row.id in seen:
                raise ValueError(f"手動行の id '{row.id}' が重複している（ID は一意・再利用しない）")
            seen.add(row.id)
        return self

    @property
    def rows_by_id(self) -> dict[str, ManualRow]:
        """手動行を ID で引く辞書（節の項目からの参照解決に使う）。"""
        return {row.id: row for row in self.rows}


def load_overlay(root: Path) -> Overlay:
    """`docs/wbs.yaml` を読む。無ければ既定（空の上書き）を返す。壊れていれば pydantic が失敗にする。

    「無ければ既定」は fail-open ではない：上書きが無い状態でも、節構成は `work/` の木から漏れなく導かれる
    （見えなくなる単位が出ない）。空振りで緑になるのは「描く対象が 1 件も無いのに成功する」経路の方で、
    そちらは `wbs.build` が拒否する。
    """
    path = root / OVERLAY_PATH
    if not path.is_file():
        return Overlay()
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return Overlay()
    if not isinstance(raw, dict):
        raise ValueError(f"{OVERLAY_PATH} の中身が対応表（キー: 値）になっていない")
    return Overlay.model_validate(raw)
