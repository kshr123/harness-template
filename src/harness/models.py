"""プロジェクト管理のデータ型（タスクの frontmatter と WBS のエピック）。

構造化データは pydantic v2 で型を検証する。壊れた frontmatter は
検証コマンドで失敗にする（＝機械が読める形を保証する）。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# エピック未割り当てを表す既定値。「あとで割り当てる」を意味する正当な状態。
NONE_EPIC = "none"


class TaskStatus(StrEnum):
    """タスクの状態。done は検証にすべて成功したときだけにする（自己申告では確定しない）。"""

    todo = "todo"
    in_progress = "in-progress"
    in_review = "in-review"
    blocked = "blocked"
    done = "done"


class PlanMaturity(StrEnum):
    """計画の詳しさ。outline（まだ分解していない）は正常な状態で、参照チェックは咎めない。"""

    outline = "outline"
    detailed = "detailed"


class Task(BaseModel):
    """タスク（個々の作業）＝存在と状態の唯一の情報源。1 タスク＝1 MD。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: TaskStatus
    epic: str = NONE_EPIC  # 所属エピック ID。未割り当ては "none"。
    requirements: list[str] = Field(default_factory=list)
    priority: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    owner: str | None = None
    mode: str | None = None  # personal | team（任意。案件既定を上書き）


class Epic(BaseModel):
    """WBS のエピック＝目的と計画の詳しさだけを手で持つ。

    配下のタスク一覧と進捗はタスクから算出する（二重に管理しない）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    plan: PlanMaturity = PlanMaturity.outline
    status: TaskStatus = TaskStatus.todo
    requirements: list[str] = Field(default_factory=list)
