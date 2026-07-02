"""PM層のデータ型（タスク frontmatter と WBS のエピック）。

構造化データは pydantic v2 で型付き検証する。壊れた frontmatter は
検証コマンドで赤にする（＝機械が読める形を保証）。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# エピック未割当を表す番兵。バックログ（割当待ち）を意味する正当な状態。
NONE_EPIC = "none"


class TaskStatus(StrEnum):
    """タスクの状態。done は「検証が緑」でのみ確定する（自己申告不可）。"""

    todo = "todo"
    in_progress = "in-progress"
    in_review = "in-review"
    blocked = "blocked"
    done = "done"


class PlanMaturity(StrEnum):
    """計画の成熟度。outline（粗い＝余白）は正常な状態で、lint は咎めない。"""

    outline = "outline"
    detailed = "detailed"


class Task(BaseModel):
    """タスク（葉）＝存在と状態の唯一の情報源。1 タスク＝1 MD。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: TaskStatus
    epic: str = NONE_EPIC  # 所属エピック ID。未割当は "none"（バックログ）。
    requirements: list[str] = Field(default_factory=list)
    priority: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    owner: str | None = None
    mode: str | None = None  # personal | team（任意。案件既定を上書き）


class Epic(BaseModel):
    """WBS のエピック＝意図（目的）と計画の成熟度だけを手で持つ。

    配下タスク一覧と進捗はタスクから導出する（二重管理しない）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    plan: PlanMaturity = PlanMaturity.outline
    status: TaskStatus = TaskStatus.todo
    requirements: list[str] = Field(default_factory=list)
