"""プロジェクト管理の中核ロジック：作業単位の木の読み込み、進捗の算出、参照チェック。

- 作業単位＝意味のある 1 まとまり（ディレクトリ、または軽いときはファイル）。親は置き場所。
- 木を再帰的にたどって階層を作り、進捗は末端の単位の状態から算出する（手書きしない・二重に管理しない）。
- 親はフォルダなので参照エラーは起きない。代わりに ID の重複・depends_on の指す先が無い、を失敗にする。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
from pydantic import ValidationError

from harness.models import Item, Kind, PlanMaturity, Status

WORK_DIR = "work"
REQUIREMENTS_DIR = "docs/requirements"
DEMANDS_DIR = "docs/demands"  # 要求層（クライアントの言葉）。要件（REQ）の satisfies が参照する上流。
MARKER = "item.md"
# 軽い単位のファイル名の印。EP- / T- / INV- / E- で始まる .md を単位とみなす（notes.md 等の付属ファイルと区別する）。
UNIT_FILE = re.compile(r"^(EP|T|INV|E)-\d+.*\.md$")
# 単位ではない成果物（説明・SPEC・PLAN・設計メモ等）の許容ファイル名。ここにも UNIT_FILE にも一致しない
# work/ 配下の .md は「正体不明」として work_tree_lint が error にする（黙認しない）。
_ARTIFACT_FILES = {MARKER, "STATUS.md", "SPEC.md", "PLAN.md", "DESIGN.md", "notes.md", "README.md"}

# 外部から起動され自分では止まらないループ（scheduled workflow 等）の「止め方」の宣言マーカー。
# 同じ書式を agent の schedule_lint（monitor.yml）と ops の ci_lint（retrain.yml）が共有するための 1 か所
# （2 つ目の書式を作らない＝T-0184）。中身の真偽までは機械には分からない＝「宣言が在るか」だけを見る
# （Registry(require_source=True) と同じ fail closed の形。書き忘れを不可能にするが、正しさは人が確かめる）。
STOP_DECLARATION_RE = re.compile(r"^\s*#\s*stop:", re.MULTILINE | re.IGNORECASE)


def has_stop_declaration(text: str) -> bool:
    """外部起動ループ（scheduled workflow）が `# stop:` コメントで停止手順を宣言しているか（書式の正本はここ）。"""
    return STOP_DECLARATION_RE.search(text) is not None


@dataclass
class Node:
    """木の 1 ノード（作業単位）。children が空なら末端。"""

    item: Item
    path: Path
    children: list[Node] = field(default_factory=list)

    def leaves(self) -> list[Node]:
        """末端の単位（実際の作業）を集める。自分が末端ならば自分。"""
        if not self.children:
            return [self]
        out: list[Node] = []
        for c in self.children:
            out.extend(c.leaves())
        return out


@dataclass(frozen=True)
class Problem:
    """検証の指摘。level="error" だけが失敗（検証を止める）。"""

    level: str  # "error" | "info"
    message: str


def _parse_item(path: Path, problems: list[Problem]) -> Item | None:
    post = frontmatter.load(path)
    try:
        return Item.model_validate(dict(post.metadata))
    except ValidationError as exc:
        rel = path.name if path.name != MARKER else f"{path.parent.name}/{MARKER}"
        problems.append(Problem("error", f"{rel}: frontmatter が不正: {exc.error_count()} 件"))
        return None


def _load_dir(dir_path: Path, problems: list[Problem]) -> list[Node]:
    """ディレクトリ直下の作業単位（子ディレクトリの item.md と、印の付いたファイル）を読む。"""
    nodes: list[Node] = []
    for entry in sorted(dir_path.iterdir()):
        if entry.is_dir():
            marker = entry / MARKER
            if marker.is_file():
                item = _parse_item(marker, problems)
                if item is not None:
                    nodes.append(Node(item, entry, _load_dir(entry, problems)))
            # item.md の無いディレクトリ（code/ results/ configs/ 等）は付属物なので単位にしない。
        elif entry.suffix == ".md" and entry.name not in _ARTIFACT_FILES and UNIT_FILE.match(entry.name):
            item = _parse_item(entry, problems)
            if item is not None:
                nodes.append(Node(item, entry, []))
    return nodes


def load_tree(root: Path) -> tuple[list[Node], list[Problem]]:
    """work/ をたどって作業単位の木を作る。"""
    problems: list[Problem] = []
    work = root / WORK_DIR
    if not work.is_dir():
        return [], problems
    return _load_dir(work, problems), problems


def _all_nodes(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    for n in nodes:
        out.append(n)
        out.extend(_all_nodes(n.children))
    return out


def _collectable_test_names(path: Path) -> set[str]:
    """テストファイルを ast で解析し、pytest が nodeid で拾える名前の集合を返す。

    数えるのは実際の定義だけ：(1) モジュール直下の関数定義名（`def test_x` → `"test_x"`）、
    (2) クラス名（`"TestFoo"`）と、クラス内メソッドの `"TestFoo::test_y"` 形。
    文字列・コメント・`# TODO: test_x を書く` のような下書きは**当たらない**（穴埋め(b) を本物にする＝
    「実在するテスト定義」だけを実在とみなす）。パースできないファイルは空集合（別途 file 検査で拾う）。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    except ValueError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    names.add(f"{node.name}::{sub.name}")
    return names


def _verified_by_problems(root: Path, item_id: str, value: str) -> list[Problem]:
    """1 つの `verified_by` 値（例 `tests/test_x.py::test_y`）を検査する。

    - `::テスト名` を必須にする。ファイル名だけの参照は「実在する無関係なファイル」でも通ってしまうため
      error にする（申告し忘れの第 1 号を見逃さない）。
    - 実在照合は ast（`_collectable_test_names`）で行う。`tests/test_x.py::TestClass::test_y`（クラス内
      メソッド）にも対応する（chain を `::` で連結して照合する）。パラメータ化の `[...]` は各節から落とす。
    """
    problems: list[Problem] = []
    parts = value.split("::")
    test_file = parts[0]
    names = parts[1:]
    target = root / test_file
    if not target.is_file():
        problems.append(Problem("error", f"{item_id}: verified_by の '{test_file}' が見つからない"))
        return problems
    if not names:
        problems.append(
            Problem(
                "error",
                f"{item_id}: verified_by の '{value}' に ::テスト名 が無い"
                f"（ファイル名だけでは実在照合できず、無関係なファイルでも通ってしまう）",
            )
        )
        return problems
    chain = [seg.split("[")[0].strip() for seg in names]  # パラメータ化 [..] を落として素の名前で照合
    if any(not seg for seg in chain):
        problems.append(Problem("error", f"{item_id}: verified_by の '{value}' のテスト名が空"))
        return problems
    ref = "::".join(chain)
    if ref not in _collectable_test_names(target):
        problems.append(
            Problem("error", f"{item_id}: verified_by の '{value}' が {test_file} に（def として）実在しない")
        )
    return problems


def _dir_is_visible(dir_path: Path, work: Path) -> bool:
    """このディレクトリが作業単位の木に見えるか（＝item.md の鎖が work/ まで途切れずに続くか）。

    `_load_dir` は work/ を起点に、item.md を持つ子ディレクトリだけを再帰する。よって work/ 自身か、
    「item.md を持ち、かつ親も見える」ディレクトリだけが木に載る。祖先のどこかに item.md が欠けると、
    その配下の単位は全 PM 検査から消える（不可視領域）。
    """
    if dir_path == work:
        return True
    if not (dir_path / MARKER).is_file():
        return False
    return _dir_is_visible(dir_path.parent, work)


def work_tree_lint(root: Path) -> list[Problem]:
    """`work/` 配下に「不可視領域」と「正体不明の .md」が無いか検査する（対象集合はファイルシステム）。

    `pm.lint` の木は item.md を持つディレクトリしかたどらないため、item.md の無いディレクトリ配下の単位は
    全検査から消える（verified_by の無い done も素通りする）。ここは木を使わず work/ 以下の全 .md を機械的に
    走査し、対象集合を申告ではなくファイルシステムから導く（(b) の条件）。error は 2 種類：
    (1) 単位（UNIT_FILE の軽い単位、または item.md を持つディレクトリ単位）を含むのに item.md の鎖が
        途切れているディレクトリ（不可視の単位）、
    (2) UNIT_FILE にも成果物のファイル名（`_ARTIFACT_FILES`）にも一致しない .md（正体不明を黙認しない）。

    ディレクトリ単位（`item.md`）も検査する：`_load_dir` は item.md を持つ子だけを再帰するので、途中の階層に
    item.md が欠けると、その奥の `item.md` を持つ単位ごと不可視になる（軽い単位の取りこぼしと同じ穴。
    item.md 自身は成果物名なので、以前は両分岐から漏れていた）。
    """
    problems: list[Problem] = []
    work = root / WORK_DIR
    if not work.is_dir():
        return problems
    invisible_dirs: set[Path] = set()

    def _flag_invisible(unit_dir: Path, unit_label: str) -> None:
        # unit_dir（この単位のあるディレクトリ）が木に載らない＝鎖が work/ まで続かないなら error。
        if not _dir_is_visible(unit_dir, work) and unit_dir not in invisible_dirs:
            invisible_dirs.add(unit_dir)
            rel = unit_dir.relative_to(root).as_posix()
            problems.append(
                Problem(
                    "error",
                    f"{rel}/: 作業単位（{unit_label}）を含むのに item.md の鎖が work/ まで続かない"
                    f"（このディレクトリの単位は全 PM 検査から不可視。祖先の各階層に item.md を置くこと）",
                )
            )

    for md in sorted(work.rglob("*.md")):
        name = md.name
        if name == MARKER:  # ディレクトリ単位。この dir 自身が可視か（＝item.md の鎖が続くか）を問う。
            _flag_invisible(md.parent, MARKER)
        elif UNIT_FILE.match(name):  # 軽い単位。置かれている dir が可視か。
            _flag_invisible(md.parent, name)
        elif name not in _ARTIFACT_FILES:
            rel = md.relative_to(root).as_posix()
            problems.append(
                Problem(
                    "error",
                    f"{rel}: 正体不明の .md（作業単位の命名 {UNIT_FILE.pattern} にも成果物 "
                    f"{sorted(_ARTIFACT_FILES)} にも一致しない）。単位なら正しい名前に、成果物なら "
                    f"_ARTIFACT_FILES に加えること",
                )
            )
    return problems


def lint(root: Path) -> list[Problem]:
    """作業単位の検査。ID の重複・depends_on の指す先が無い・計画の詳しさの不整合を見る。"""
    top, problems = load_tree(root)
    everything = _all_nodes(top)

    # ID の重複＝失敗（一意・再利用しないため）。
    seen: dict[str, Path] = {}
    for n in everything:
        if n.item.id in seen:
            problems.append(Problem("error", f"{n.item.id}: ID が重複している（一意にすること）"))
        seen[n.item.id] = n.path

    # depends_on の指す先が無い＝参照エラー（失敗）。
    known = set(seen)
    for n in everything:
        for dep in n.item.depends_on:
            if dep not in known:
                problems.append(Problem("error", f"{n.item.id}: depends_on の '{dep}' が見つからない（参照エラー）"))

    # depends_on の循環（A→B→A）＝失敗。両端が実在すると上の参照チェックは通るため、DFS（白/灰/黒）で検出する。
    # 再帰でなく明示スタックの反復 DFS（深い依存鎖でも RecursionError で門番が落ちない）。
    graph = {n.item.id: [d for d in n.item.depends_on if d in known] for n in everything}
    color = dict.fromkeys(graph, 0)  # 0=白（未訪問）／1=灰（訪問中）／2=黒（確定）
    for start in graph:
        if color[start] != 0:
            continue
        path: list[str] = []
        dfs: list[tuple[str, int]] = [(start, 0)]  # (ノード, 次に見る子の添字)
        while dfs:
            node_id, idx = dfs[-1]
            if idx == 0:  # このノードの初回訪問時だけ灰にして経路へ積む
                color[node_id] = 1
                path.append(node_id)
            if idx < len(graph[node_id]):
                dfs[-1] = (node_id, idx + 1)
                dep = graph[node_id][idx]
                if color[dep] == 0:
                    dfs.append((dep, 0))
                elif color[dep] == 1:  # 灰へ戻る辺＝循環
                    cycle = [*path[path.index(dep) :], dep]
                    problems.append(Problem("error", f"{dep}: depends_on が循環している（{' → '.join(cycle)}）"))
            else:  # 子を見終えた＝確定（黒）にして経路から降ろす
                color[node_id] = 2
                path.pop()
                dfs.pop()

    # requirements の指す先が無い＝参照エラー（失敗）。depends_on の検査と対称にする。
    # docs/requirements/ が無い案件では要件の検査そのものを行わない（要件文書を持たない案件を咎めない）。
    req_dir = root / REQUIREMENTS_DIR
    if req_dir.is_dir():
        # ID は先頭の REQ-<番号>。ファイル名は REQ-001.md でも REQ-001-<短い説明>.md でもよい（単位の命名規則と対称）。
        known_reqs = {m.group() for p in req_dir.glob("REQ-*.md") if (m := re.match(r"REQ-\d+", p.stem))}
        referenced: set[str] = set()
        for n in everything:
            for req in n.item.requirements:
                referenced.add(req)
                if req not in known_reqs:
                    problems.append(
                        Problem("error", f"{n.item.id}: requirements の '{req}' が見つからない（参照エラー）")
                    )
        # どの単位からも参照されない要件＝未カバーの要件。計画中（未分解）は正常なので失敗にはしない。
        for req in sorted(known_reqs - referenced):
            problems.append(Problem("info", f"{req}: 未カバーの要件（どの単位からも参照されていない）"))

    # 要求→要件のトレース：REQ の satisfies が実在する DEM（要求）を指すこと（要件→作業の参照検査と対称・上流側）。
    # fail-closed：satisfies を書いたら実在 DEM-<番号> のみ許す。要求層（docs/demands/）が無くても
    # （fork で空ディレクトリが git から消えても）非空の satisfies は参照エラーにする＝「書いても黙って緑」を作らない。
    # satisfies を書かない案件は今までどおり何も要求されない。
    if req_dir.is_dir():
        dem_dir = root / DEMANDS_DIR
        known_dems = (
            {dm.group() for p in dem_dir.glob("DEM-*.md") if (dm := re.match(r"DEM-\d+", p.stem))}
            if dem_dir.is_dir()
            else set()
        )
        for rp in sorted(req_dir.glob("REQ-*.md")):
            rm = re.match(r"REQ-\d+", rp.stem)
            rid = rm.group() if rm else rp.name
            try:
                satisfies = frontmatter.load(rp).metadata.get("satisfies")
            except Exception:  # noqa: BLE001  壊れた frontmatter はクラッシュでなく Problem にする（うるさく失敗）
                problems.append(Problem("error", f"{rid}: frontmatter が読めない（satisfies の検査）"))
                continue
            if satisfies is None or satisfies == []:
                continue
            if not isinstance(satisfies, list):
                problems.append(Problem("error", f"{rid}: satisfies は DEM-<番号> の配列にする（今の値は不正）"))
                continue
            for dem in satisfies:
                if not (isinstance(dem, str) and re.fullmatch(r"DEM-\d+", dem)):
                    problems.append(Problem("error", f"{rid}: satisfies の '{dem}' が DEM-<番号> の形でない"))
                elif dem not in known_dems:
                    problems.append(Problem("error", f"{rid}: satisfies の '{dem}' が見つからない（参照エラー）"))

    # 完了↔検証の結びつけ：done のタスクは、対応するテスト（verified_by）を持ち、それが存在すること。
    # これにより「テストを書かずに done にする」自己申告完了を機械的に防ぐ。
    for n in everything:
        if n.item.kind is Kind.task and n.item.status is Status.done:
            if not n.item.verified_by:
                problems.append(Problem("error", f"{n.item.id}: done だが verified_by（対応するテスト）が無い"))
            for v in n.item.verified_by:
                problems += _verified_by_problems(root, n.item.id, v)

    # 調査は done のとき、本文に「結論」の節が必須（verified_by の代わり。②自動検証）。
    for n in everything:
        if n.item.kind is Kind.investigation and n.item.status is Status.done:
            src = n.path if n.path.is_file() else n.path / MARKER
            if "## 結論" not in frontmatter.load(src).content:
                problems.append(Problem("error", f"{n.item.id}: done の調査に「## 結論」の節が無い"))

    # 実験は done のとき、結果記録（results/ の指標・設定・データ指紋）が必須（調査の「## 結論」検査と同型）。
    # 実験はフォルダ単位で再現一式を同居させる約束なので、ファイル単位の done は記録の置き場が無く失敗にする。
    for n in everything:
        if n.item.kind is Kind.experiment and n.item.status is Status.done:
            if n.path.is_file():
                problems.append(
                    Problem("error", f"{n.item.id}: done の実験はフォルダ単位で results/ に結果を同居させること")
                )
                continue
            results = n.path / "results"
            if not (results.is_dir() and any(results.iterdir())):
                problems.append(
                    Problem("error", f"{n.item.id}: done の実験に結果記録（results/ の指標・設定・データ指紋）が無い")
                )

    # plan=detailed なのに子の単位が無い＝分解し忘れの可能性（失敗にはしない）。
    for n in everything:
        if n.item.plan is PlanMaturity.detailed and n.item.kind is Kind.epic and not n.children:
            problems.append(Problem("info", f"{n.item.id}: plan=detailed だが子の単位が無い（分解し忘れの可能性）"))
        # outline で子が無い＝まだ分解していないだけ。何も言わない。

    # 日程の整合（顧客向けの WBS・ガントの材料。日付は任意なので、置いたときだけ矛盾を咎める）。
    for n in everything:
        it = n.item
        if it.start is not None and it.due is not None and it.start > it.due:
            problems.append(
                Problem("error", f"{it.id}: start（{it.start}）が due（{it.due}）より後（開始は終了以前にする）")
            )
        if it.milestone and it.due is None:
            problems.append(Problem("error", f"{it.id}: milestone だが due（期日）が無い（節目は期日を持つ）"))

    # work/ の不可視領域・正体不明の .md（木をたどらずファイルシステムから対象集合を導く）。
    problems += work_tree_lint(root)

    return problems


def render_status(root: Path, extra_pending: list[str] | None = None) -> str:
    """作業単位の木から STATUS.md（自動生成のファイル）を算出する。手書き禁止。

    extra_pending は課題など、木の外から集約する「人の判断待ち」の行（呼び出し側が渡す）。
    """
    top, _ = load_tree(root)

    lines: list[str] = [
        "<!-- 自動生成：uv run status が作る。手で編集しないこと。 -->",
        "# STATUS（作業単位の進捗＋計画の詳しさ）",
        "",
        "| 単位 | 種類 | plan | done/総数 | blocked | 関連要件 |",
        "|---|---|---|---|---|---|",
    ]
    for node in top:
        _render_node(node, lines, depth=0)

    # 人の判断待ち（承認待ち・止まっている・未解決の質問）を集約する。
    # 人はここを見れば「要所が来た」と分かる（見に行かないと分からない状態を減らす）。
    pending: list[str] = []
    for n in _all_nodes(top):
        if n.item.status is Status.blocked:
            pending.append(f"- {n.item.display}：止まっている（blocked）")
        elif n.item.status is Status.in_review:
            pending.append(f"- {n.item.display}：承認待ち（in-review）")
    work = root / WORK_DIR
    if work.is_dir():
        for md in sorted(work.rglob("*.md")):
            if "[要確認]" in md.read_text(encoding="utf-8"):
                pending.append(f"- {md.relative_to(root)}：未解決の [要確認] あり")
    if extra_pending:
        pending.extend(extra_pending)

    lines.append("")
    lines.append("## 人の判断待ち")
    lines.extend(pending if pending else ["（なし）"])
    lines.append("")
    return "\n".join(lines)


def next_actionable(root: Path) -> tuple[list[Node], list[Node], list[tuple[Node, list[str]]], list[Node]]:
    """「次に何に着手できるか」を木から算出する（着手順は plan／依存で足りるが、探す手間を省く提案）。

    4 つに分ける（末端の作業単位＝task/experiment/investigation を対象にする。epic はコンテナ扱い）：
    - in_progress：仕掛かり中の末端単位（status=in-progress）。再開の候補＝新規着手より先に片づける。
    - ready：着手できる末端単位（status=todo・depends_on が全て done）。
    - waiting：やりたいが依存待ちの末端単位（todo だが未完の depends_on を持つ）。各単位に未完の依存 ID を添える。
    - to_outline：分解の候補（outline のままの epic）。着手の前にまず detailed へ割る対象。
    提案であって門番ではない（status は生成物。ここで verify を止めたりしない）。仕掛かり中は時間経過で検査を落とす
    ような閾値にはしない（生成物の一致ゲートを撤去したのと同じ、非決定的な赤の再発明を避ける）＝可視化にとどめる。

    どの節も並びは優先度（人が置く判断）→ ID の順。優先度を置かなければ全て中位で並びは ID 順のまま
    （既定の挙動を保つ）。分解の候補（to_outline）も同じ＝epic に置いた優先度も静かに捨てず並べ替えに運ぶ。
    """
    top, _ = load_tree(root)
    nodes = _all_nodes(top)
    status_by_id = {n.item.id: n.item.status for n in nodes}
    # 末端の「作業」単位＝着手・再開の対象。epic はコンテナ（分解の候補は下で別扱い）。
    leaf_work_kinds = (Kind.task, Kind.experiment, Kind.investigation)
    in_progress: list[Node] = []
    ready: list[Node] = []
    waiting: list[tuple[Node, list[str]]] = []
    to_outline: list[Node] = []
    for n in nodes:
        # コンテナ（子を持つ epic）は着手単位でない＝既に分解済み。outline のまま子を持つのは分解の途中なので、
        # 「分解の候補」には末端（子なし）の outline epic だけを挙げる。
        if n.children:
            continue
        if n.item.kind is Kind.epic and n.item.plan is PlanMaturity.outline and n.item.status is not Status.done:
            to_outline.append(n)
            continue
        if n.item.kind not in leaf_work_kinds:
            continue
        if n.item.status is Status.in_progress:
            in_progress.append(n)
            continue
        if n.item.status is not Status.todo:
            continue
        unmet = [d for d in n.item.depends_on if status_by_id.get(d) is not Status.done]
        (waiting.append((n, unmet)) if unmet else ready.append(n))

    def by_priority_then_id(n: Node) -> tuple[int, str]:
        return (n.item.priority_rank, n.item.id)

    in_progress.sort(key=by_priority_then_id)
    ready.sort(key=by_priority_then_id)
    waiting.sort(key=lambda nu: by_priority_then_id(nu[0]))
    to_outline.sort(key=by_priority_then_id)
    return in_progress, ready, waiting, to_outline


def _next_line(node: Node) -> str:
    """`status --next` の 1 行。優先度を置いた単位だけ印を添える（無指定は既定＝印なし）。"""
    mark = f"［優先度: {node.item.priority.value}］" if node.item.priority else ""
    return f"- {node.item.display}{mark}"


def render_next(root: Path) -> str:
    """next_actionable を人が読む文へ。`uv run status --next` の出力。"""
    in_progress, ready, waiting, to_outline = next_actionable(root)
    lines: list[str] = ["# 次に着手できる作業単位（提案・門番ではない）", ""]
    lines.append("## 仕掛かり中（in-progress・再開の候補＝新規着手より先に）")
    lines.extend([_next_line(n) for n in in_progress] if in_progress else ["（なし）"])
    lines.append("")
    lines.append("## いま着手できる（todo・依存は満たされている）")
    lines.extend([_next_line(n) for n in ready] if ready else ["（なし）"])
    lines.append("")
    lines.append("## 依存待ち（todo だが未完の depends_on がある）")
    lines.extend([f"{_next_line(n)}（待ち: {', '.join(unmet)}）" for n, unmet in waiting] if waiting else ["（なし）"])
    lines.append("")
    lines.append("## 分解の候補（outline のままの epic）")
    lines.extend([_next_line(n) for n in to_outline] if to_outline else ["（なし）"])
    return "\n".join(lines)


def _render_node(node: Node, lines: list[str], depth: int) -> None:
    leaves = node.leaves()
    is_container = bool(node.children)
    total = len(leaves)
    done = sum(1 for lf in leaves if lf.item.status is Status.done)
    blocked = sum(1 for lf in leaves if lf.item.status is Status.blocked)

    if node.item.plan is PlanMaturity.outline and not is_container and node.item.kind is Kind.epic:
        progress = "—（未分解）"
    elif is_container:
        progress = f"{done}/{total}" + (" ✅" if total and done == total else "")
    else:
        progress = "1/1 ✅" if node.item.status is Status.done else f"0/1（{node.item.status.value}）"

    plan = node.item.plan.value if node.item.kind in (Kind.epic, Kind.experiment) else "—"
    reqs = ", ".join(node.item.requirements) if node.item.requirements else "—"
    indent = "　" * depth
    lines.append(f"| {indent}{node.item.display} | {node.item.kind.value} | {plan} | {progress} | {blocked} | {reqs} |")
    for child in node.children:
        _render_node(child, lines, depth + 1)


def spec_lint(root: Path) -> list[Problem]:
    """作業単位に SPEC.md があれば、必要な見出しがそろっているか確認する。

    SPEC は任意（無くてもよい）。ただし置いたら中身が欠けないようにする。
    """
    required = ["## 目的", "## 受け入れ基準", "## やらないこと", "## 最後の確認手順"]
    problems: list[Problem] = []
    for spec in sorted((root / WORK_DIR).rglob("SPEC.md")):
        text = spec.read_text(encoding="utf-8")
        missing = [h for h in required if h not in text]
        if missing:
            problems.append(Problem("error", f"{spec.parent.name}/SPEC.md: 必要な見出しが不足: {', '.join(missing)}"))
    return problems
