"""作業単位のデータ型（エピック・タスク・実験に共通の item）。

意味のある 1 まとまり＝1 ディレクトリ（または軽いときは 1 ファイル）。
親は「そのファイルの置き場所（ディレクトリ）」で表す。frontmatter に親の欄は持たない。
構造化データは pydantic v2 で型を検証する。壊れた frontmatter は検証コマンドで失敗にする。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Kind(StrEnum):
    """作業単位の種類。"""

    epic = "epic"  # 大きな束（複数セッションにまたがる。子の単位を持つ）
    task = "task"  # 工学的な 1 つの変更（1 PR で完結）
    experiment = "experiment"  # 1 つの仮説を試す単位（結果を同居させ、比べる）


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
    priority: str | None = None
    owner: str | None = None

    @property
    def display(self) -> str:
        return f"{self.id} {self.title}" if self.title else self.id
