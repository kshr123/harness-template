"""作業単位のデータ型（エピック・タスク・実験に共通の item）。

意味のある 1 まとまり＝1 ディレクトリ（または軽いときは 1 ファイル）。
親は「そのファイルの置き場所（ディレクトリ）」で表す。frontmatter に親の欄は持たない。
構造化データは pydantic v2 で型を検証する。壊れた frontmatter は検証コマンドで失敗にする。
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Kind(StrEnum):
    """作業単位の種類。分ける基準は完了条件・生涯・成果物のいずれかの違い。"""

    epic = "epic"  # 大きな束（複数セッションにまたがる。子の単位を持つ）
    task = "task"  # 1 つの変更（1 PR で完結。完了＝検証成功＋verified_by）
    investigation = "investigation"  # 調査（成果物＝知見・決定。完了＝結論の記録。verified_by 不要）
    experiment = "experiment"  # 1 つの仮説を試す単位（結果を同居させ、比べる。再現一式を持つ）


class Status(StrEnum):
    """作業単位の状態。done は検証にすべて成功したときだけにする（自己申告では確定しない）。"""

    todo = "todo"
    in_progress = "in-progress"
    in_review = "in-review"
    blocked = "blocked"
    done = "done"


class PlanMaturity(StrEnum):
    """計画の詳しさ。outline（まだ分解していない）は正常な状態で、検査は咎めない。"""

    outline = "outline"
    detailed = "detailed"


class Priority(StrEnum):
    """着手の優先度。人が置く判断（機械は決めず、置かれた順位を並べ替えに運ぶだけ）。

    未知の値は検証で失敗する（保証 (a)＝構造的に不可能）ので、自由文字列のタイポは done にならない。
    無指定は normal と同じ扱い＝並びは既定の ID 順のまま（優先度を置いた単位だけが上下する）。
    """

    high = "high"
    normal = "normal"
    low = "low"


# 並べ替え用の順位（小さいほど先）。無指定（None）は normal と同じ中位＝優先度を置かなければ ID 順を保つ。
_PRIORITY_RANK = {Priority.high: 0, Priority.normal: 1, Priority.low: 2}


class Item(BaseModel):
    """1 つの作業単位（item.md、または軽い単位のファイル）の frontmatter。"""

    model_config = ConfigDict(extra="forbid")

    id: str  # 例 EP-01 / T-0007 / E-0003。一意・再利用しない。
    kind: Kind
    status: Status
    title: str | None = None  # 表示名。無ければ id を使う。
    plan: PlanMaturity = PlanMaturity.outline  # epic / experiment の計画の詳しさ
    requirements: list[str] = Field(default_factory=list)  # 満たす要件 ID（REQ-xxx）
    depends_on: list[str] = Field(default_factory=list)  # 先行する単位の ID
    # 受け入れ基準を確かめるテストの場所（例 tests/test_foo.py::test_bar）。
    # done のタスクは、これが空でなく、指すテストが存在することを要求する（完了↔検証の結びつけ）。
    verified_by: list[str] = Field(default_factory=list)
    # 作成日・完了日。時系列の並べ替えの材料にする（設計「時系列の扱い」）。
    created: date | None = None
    closed: date | None = None
    priority: Priority | None = None  # 着手の優先度（人が置く）。status --next の並べ替えに使う。
    owner: str | None = None  # 担当（1 名）。顧客向けの WBS では名簿から選ぶ。
    team: str | None = None  # 担当チーム。顧客向けの WBS の区分に使う（owner と対称の任意欄）。
    # 顧客向けの WBS・スケジュール（ガント）の材料。すべて任意＝無指定は正常（全単位に日付を強制しない）。
    # 語は PMBOK / MS Project / GitHub の標準に合わせる（造語しない）。%完了・実績日付は**保存しない**
    # ＝進捗は木から（done 末端/総末端）、実績は created/closed から導出する（status と二重台帳にしない）。
    start: date | None = None  # 予定開始（Start）
    due: date | None = None  # 予定終了（Finish／GitHub の due date）
    effort_days: float | None = Field(default=None, gt=0)  # 見積り工数（人日／Work）。正の値のみ（負・NaN は失敗）
    milestone: bool = False  # マイルストーン（期間ゼロの節目。Milestone）

    @property
    def display(self) -> str:
        return f"{self.id} {self.title}" if self.title else self.id

    @property
    def priority_rank(self) -> int:
        """並べ替え用の優先度の順位（小さいほど先）。無指定は normal と同じ中位。"""
        return 1 if self.priority is None else _PRIORITY_RANK[self.priority]
