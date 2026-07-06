"""汎用レジストリ（config の kind 文字列 → 工場）の共通形。DS の 9 レジストリを 1 つの形に揃える。

- 各項目は `Entry`（factory＋description＋task＋tags）。説明文は factory の docstring 1 行目から自動で取る
  （無ければ登録時に ValueError＝「部品は入口まで作って完了」DEC-0009 を登録時点で強制する）。
  クラス工場は**自前の** `__doc__` だけを見る（親の docstring を継承して空振りさせない・test_catalog の規約）。
- `Registry` は `Mapping[str, Entry]`：`in`・`sorted()`・`len()`・`.items()` がそのまま効く（既存の呼び方を壊さない）。
- 未知 kind のエラーは `resolve` の 1 か所（候補一覧＋カタログコマンド案内＋optional extra の導入ヒント）。
- ここは中核（ds に依存しない）。ds 側は定数名（MODELS/ENCODERS/…）を保ったまま Registry インスタンスに差し替える。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast


@dataclass(frozen=True, kw_only=True)
class Entry:
    """レジストリ 1 項目。description はカタログ（`uv run data <一覧>`）に載る 1 行（DEC-0009）。

    task：この部品が解ける課題（モデルの classification/regression 等）。無関係なレジストリは None のまま。
    tags：自由な分類ラベル（現状は空が既定・カタログの絞り込み用の拡張点）。
    """

    factory: Callable[..., Any]
    description: str
    task: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class MetricEntry(Entry):
    """指標の項目（旧 eval.Metric を Entry に畳み込んだもの）。factory は sklearn.metrics の薄い包み。

    input：factory に何を渡すか。score=確率・label=閾値後のラベル・value=回帰の予測値。
    higher_is_better：合否判定（passes）の向き。回帰の rmse/log_loss は False（小さいほど良い）。
    tasks：この指標が測れる課題の並び（語彙は binary | multiclass | regression。
    例：accuracy は ("binary", "multiclass")・macro_f1 は ("multiclass",)・rmse は ("regression",)）。
    """

    input: Literal["score", "label", "value"]
    higher_is_better: bool
    tasks: tuple[str, ...]

    @property
    def fn(self) -> Callable[..., Any]:
        """旧 Metric.fn 互換の別名（analysis 等が fn で参照する）。実体は factory と同じもの。"""
        return self.factory


def _own_doc(factory: Callable[..., Any]) -> str | None:
    """factory 自前の docstring を返す。クラスは自分の __dict__ だけを見る（親の docstring を継承しない）。"""
    if isinstance(factory, type):
        doc = factory.__dict__.get("__doc__")
        return doc if isinstance(doc, str) else None
    return factory.__doc__


class Registry[E: Entry](Mapping[str, E]):
    """kind 文字列 → Entry の読み取り専用 Mapping（登録は register だけ・上書き不可）。

    name はエラー文の主語（例「モデル」→「未知のモデル '...'」）。catalog は一覧コマンド
    （例 "data models"）。extras_hint は optional 依存の kind → extra 名（未導入で使われたときの導入ヒント）。
    """

    def __init__(self, name: str, *, catalog: str, extras_hint: Mapping[str, str] | None = None) -> None:
        self.name = name
        self.catalog = catalog
        self.extras_hint: dict[str, str] = dict(extras_hint or {})
        self._entries: dict[str, E] = {}

    def register(
        self,
        kind: str,
        factory: Callable[..., Any],
        *,
        description: str | None = None,
        task: str | None = None,
        tags: Sequence[str] = (),
        entry_cls: type[E] | None = None,
        **extra: Any,  # noqa: ANN401  entry_cls（MetricEntry 等）の追加フィールドへ素通し
    ) -> None:
        """項目を 1 つ登録する。description 省略時は factory の docstring 1 行目（無ければ ValueError）。"""
        if kind in self._entries:
            raise ValueError(f"{self.name} '{kind}' は登録済み（kind は一意・上書き不可）")
        if description is None:
            doc = _own_doc(factory)
            description = doc.strip().splitlines()[0].strip() if doc else ""
        if not description:
            raise ValueError(
                f"{self.name} '{kind}' に説明文が無い（factory の docstring 1 行目か description= が必須。"
                "説明文が無いとカタログに載れない＝DEC-0009 に反する）"
            )
        # 既定の Entry は E の下限（bound）。entry_cls 未指定のレジストリは Registry[Entry] として使う前提。
        cls = entry_cls if entry_cls is not None else cast("type[E]", Entry)
        self._entries[kind] = cls(factory=factory, description=description, task=task, tags=tuple(tags), **extra)

    def resolve(self, kind: object) -> E:
        """kind から Entry を引く。未知 kind の ValueError はここ 1 か所（候補＋カタログ案内＋extra ヒント）。"""
        if isinstance(kind, str):
            entry = self._entries.get(kind)
            if entry is not None:
                return entry
        extra = self.extras_hint.get(kind) if isinstance(kind, str) else None
        hint = f"。'{kind}' は `uv sync --extra {extra}` で使えるようになる" if extra else ""
        raise ValueError(
            f"未知の{self.name} '{kind}'（{sorted(self._entries)} のいずれか・一覧は `uv run {self.catalog}`）{hint}"
        )

    def build(
        self,
        spec: Mapping[str, Any],
        *,
        seed: int,
        task: str | None = None,
        drop: Sequence[str] = ("kind", "name", "columns"),
    ) -> Any:  # noqa: ANN401  工場の返り値（sklearn 推定器等）へ素通し
        """config の 1 節（{kind, ...params}）から部品を 1 つ作る＝factory(seed, **params)。

        drop のキー（kind と、配線用の name/columns）は params に渡さない。task を渡すと Entry.task と
        突き合わせて実行前に止める（例：回帰モデル×分類 task）。
        """
        kind = spec.get("kind")
        entry = self.resolve(kind)
        if task is not None and entry.task != task:
            raise ValueError(f"{self.name} '{kind}' は {entry.task} 用（この実験は task: {task}）")
        params = {k: v for k, v in spec.items() if k not in drop}
        return entry.factory(seed, **params)

    # --- Mapping の実装（`in`・sorted()・len()・.items() が効く） ---

    def __getitem__(self, key: str) -> E:
        return self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def render_catalog(
    registry: Registry[Any], *, show_task: bool = False, show_params: bool = False, prefix: str = ""
) -> None:
    """レジストリを 1 行 1 項目（タブ区切り）で出す共通レンダラ（ds・agent の全カタログコマンドが使う）。

    列は kind［・task］［・向き（指標のみ）］［・引数一覧］・説明文。説明文はレジストリが登録時に
    docstring 1 行目から確定させている（空は登録できない＝DEC-0009）。prefix は data unsupervised の
    グループ名（dimred/cluster/anomaly）用。ds/cli.py から引き上げた（二重管理を作らない＝DEC-0009）。
    """
    import inspect

    import typer

    for kind, entry in sorted(registry.items()):
        parts: list[str] = [prefix, kind] if prefix else [kind]
        if show_task:
            parts.append(entry.task or "-")
        if isinstance(entry, MetricEntry):  # 指標だけ合否の向きを併記（passes が読む属性）
            parts.append("大きいほど良い" if entry.higher_is_better else "小さいほど良い")
        if show_params:
            params = [p for p in inspect.signature(entry.factory).parameters if p != "self"]
            parts.append(f"({', '.join(params)})")
        parts.append(entry.description)
        typer.echo("\t".join(parts))
