"""code_doc_lint のテスト：プロファイルの公開モジュールが正本ドキュメントに載っているか。

期待値はすべて一時プロジェクトの構成（どのプロファイルにどのモジュール・どの docs を置くか）から導く。
最後の 1 本は現リポに対する回帰テスト（全プロファイルの公開モジュールが docs で触れられていること＝
以後の触れ忘れを止める）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import code_doc_lint

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in code_doc_lint.run_checks(root) if p.level == "error"]


def _profile(root: Path, name: str, *modules: str) -> None:
    """プロファイル（profile.py つきディレクトリ）と、その公開モジュールを作る。"""
    _write(root, f"src/harness/{name}/__init__.py", "")
    _write(root, f"src/harness/{name}/profile.py", "PROFILE = object()\n")
    for module in modules:
        _write(root, f"src/harness/{name}/{module}", "")


# --- 検出：ドキュメントで触れられていない公開モジュールは error ---


@pytest.mark.unit
def test_undocumented_module_is_error(tmp_path: Path) -> None:
    _profile(tmp_path, "ds", "pipeline.py", "cv.py")
    _write(tmp_path, "docs/ds.md", "実装の説明。`pipeline.py` は組み立ての中核。\n")
    errors = _errors(tmp_path)
    # pipeline.py は触れられている＝出ない。cv.py は未記載＝出る。
    assert not any("pipeline.py" in m for m in errors)
    assert any("src/harness/ds/cv.py" in m for m in errors)
    # docs に 1 行足すと消える（-code.md 側でも可）。
    _write(tmp_path, "docs/ds-code.md", "`cv.py` は交差検証。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_private_and_dunder_modules_are_ignored(tmp_path: Path) -> None:
    # `__init__.py`・`profile.py`・`_` 始まりは対象外（profile.py は説明不要な結線・私的は非公開）。
    _profile(tmp_path, "serve", "_internal.py")
    _write(tmp_path, "docs/serve.md", "配信の説明（モジュール名は書かない）。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_non_profile_subdirectories_are_not_scanned(tmp_path: Path) -> None:
    # profile.py を持たない**下位ディレクトリ**は対象外のまま（core の走査は src/harness/*.py＝非再帰）。
    # 旧 test_non_profile_dirs_are_not_scanned は「core 直下も対象外」を表明していたが、docs/core.md が
    # 存在しなかったからで、T-0167 でそれが出来たので T-0168 が仕様を反転させた（下の core の節を参照）。
    _write(tmp_path, "src/harness/util/__init__.py", "")
    _write(tmp_path, "src/harness/util/helper.py", "")  # profile.py が無い
    assert _errors(tmp_path) == []


# --- core 直下（プロファイルでない共通部品）は docs/core.md に載っているか ---


@pytest.mark.unit
def test_undocumented_core_module_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/pm.py", "")
    _write(tmp_path, "src/harness/fingerprint.py", "")
    _write(tmp_path, "docs/core.md", "中核の説明。`pm.py` は作業単位の管理。\n")
    errors = _errors(tmp_path)
    assert not any("pm.py" in m for m in errors)
    assert any("src/harness/fingerprint.py" in m for m in errors)
    assert any("docs/core.md" in m for m in errors)  # どこに書けばよいかを名指しする
    # docs に 1 行足すと消える（core-code.md 側でも可＝プロファイルと同じ「連結して探す」方式）。
    _write(tmp_path, "docs/core-code.md", "`fingerprint.py` は入力の指紋。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_core_init_and_private_modules_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "src/harness/__init__.py", "")
    _write(tmp_path, "src/harness/_private.py", "")
    _write(tmp_path, "docs/core.md", "モジュール名は書かない。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_core_cli_is_scanned(tmp_path: Path) -> None:
    # cli.py はプロファイル側でも除外されていない（除外は __init__.py と profile.py だけ）。core も対称にする。
    _write(tmp_path, "src/harness/cli.py", "")
    _write(tmp_path, "docs/core.md", "モジュール名は書かない。\n")
    assert any("src/harness/cli.py" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_profile_module_is_not_reported_against_the_core_doc(tmp_path: Path) -> None:
    # プロファイル配下のモジュールは docs/core.md でなく、そのプロファイルの正本を見る（対象がずれない）。
    _profile(tmp_path, "ds", "cv.py")
    _write(tmp_path, "docs/core.md", "`cv.py` と書いてあっても ds の正本ではない。\n")
    assert any("src/harness/ds/cv.py" in m and "docs/ds.md" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_core_exempt_key_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 免除の鍵はリポジトリ相対のパス（中核とプロファイルで名前空間が衝突しない）。
    _write(tmp_path, "src/harness/legacy.py", "")
    _write(tmp_path, "docs/core.md", "モジュール名は書かない。\n")
    assert any("src/harness/legacy.py" in m for m in _errors(tmp_path))
    monkeypatch.setitem(code_doc_lint._EXEMPT, "src/harness/legacy.py", "撤去予定なので docs から外す（ISS-9999）")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_substring_of_sibling_does_not_mask_module(tmp_path: Path) -> None:
    # `lint.py` は `schedule_lint.py` の部分文字列。素朴な部分一致だと schedule_lint.py への言及だけで
    # lint.py が「載っている」ことにされ検査が無効化される。語境界を要求して独立に必要と分かること。
    _profile(tmp_path, "agent", "lint.py", "schedule_lint.py")
    _write(tmp_path, "docs/agent.md", "`schedule_lint.py` は雛形の lint。\n")  # lint.py には触れていない
    errors = _errors(tmp_path)
    assert any("agent/lint.py" in m for m in errors)
    assert not any("schedule_lint.py" in m for m in errors)
    # lint.py を独立に書けば消える。
    _write(tmp_path, "docs/agent-code.md", "`lint.py` は宣言の lint。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_path_mention_of_a_different_module_does_not_count(tmp_path: Path) -> None:
    # 中核の `models.py` と DS の `ds/models.py` は同名の別物。docs/core.md が後者への**パス**にしか触れて
    # いないとき、前者を「載っている」と判定してはいけない（語境界が `/` を通すと守りが黙って消える）。
    _write(tmp_path, "src/harness/models.py", "")
    _profile(tmp_path, "ds", "models.py")
    _write(tmp_path, "docs/core.md", "`src/harness/ds/models.py` とは別物である。\n")
    _write(tmp_path, "docs/ds.md", "`models.py` は学習済みモデルの保存。\n")
    errors = _errors(tmp_path)
    assert any(m.startswith("src/harness/models.py:") for m in errors)  # 中核はまだ未記載
    assert not any(m.startswith("src/harness/ds/models.py:") for m in errors)  # ds は素の名前で記載済み


@pytest.mark.unit
def test_full_path_mention_of_the_module_itself_counts(tmp_path: Path) -> None:
    # 自分自身の置き場をパスで書いた言及は「載っている」（散文が `src/harness/pm.py` と書く形を壊さない）。
    _write(tmp_path, "src/harness/pm.py", "")
    _write(tmp_path, "docs/core.md", "実体は `src/harness/pm.py`。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_relative_path_mention_of_the_module_itself_counts(tmp_path: Path) -> None:
    # `ds/cv.py` のような短い形も自分自身の置き場を指すので数える（親ディレクトリを含む接尾辞なら可）。
    _profile(tmp_path, "ds", "cv.py")
    _write(tmp_path, "docs/ds.md", "交差検証は `ds/cv.py`。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_code_doc_only_covers_module(tmp_path: Path) -> None:
    # 正本は <名>.md か <名>-code.md のどちらでもよい（連結して探す）。
    _profile(tmp_path, "agent", "runtime.py")
    _write(tmp_path, "docs/agent.md", "契約の地図（モジュール名は書かない）。\n")
    assert any("runtime.py" in m for m in _errors(tmp_path))
    _write(tmp_path, "docs/agent-code.md", "`runtime.py` は往復ループ。\n")
    assert _errors(tmp_path) == []


# --- 逆向き（T-0206）：役割一覧が挙げるモジュールが実在するか（消したのに行が残る腐りを止める） ---


@pytest.mark.unit
def test_reverse_stale_table_row_is_error(tmp_path: Path) -> None:
    # core.md の役割一覧（表）が挙げる ghost.py が実在しない＝逆向きの error。実在する pm.py は出ない。
    _write(tmp_path, "src/harness/pm.py", '"""進捗."""\n')
    _write(
        tmp_path,
        "docs/core.md",
        "## モジュール一覧\n| モジュール | 役割 |\n| --- | --- |\n| `pm.py` | 進捗 |\n| `ghost.py` | 消えたはず |\n",
    )
    errors = _errors(tmp_path)
    assert any("ghost.py" in m and "実在しない" in m for m in errors)
    assert not any("pm.py`" in m for m in errors)  # 実在する行は出ない
    # 行を消せば緑（消したモジュールの説明も消す、が正しい始末）。
    _write(tmp_path, "docs/core.md", "## モジュール一覧\n| モジュール | 役割 |\n| --- | --- |\n| `pm.py` | 進捗 |\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_reverse_stale_bullet_row_is_error(tmp_path: Path) -> None:
    # プロファイルの -code.md は箇条書き（`- `X.py` … `）で役割を書く。挙げた gone.py が無ければ error。
    _profile(tmp_path, "ds", "cv.py")
    _write(tmp_path, "docs/ds.md", "`cv.py` は交差検証。\n")  # 順向きを満たす
    _write(tmp_path, "docs/ds-code.md", "- `cv.py` … 交差検証。\n- `gone.py` … 消えたモジュール。\n")
    errors = _errors(tmp_path)
    assert any("gone.py" in m and "src/harness/ds/gone.py" in m for m in errors)
    assert not any("cv.py`" in m and "実在しない" in m for m in errors)


@pytest.mark.unit
def test_reverse_ignores_prose_mentions(tmp_path: Path) -> None:
    # 散文の途中の言及（行頭が表・箇条書きでない）は逆向きの対象外＝架空名の例示で誤検出しない。
    _write(tmp_path, "src/harness/pm.py", '"""進捗."""\n')
    _write(
        tmp_path,
        "docs/core.md",
        "`pm.py` は進捗。例えば `imaginary.py` のような名前を散文で挙げても表の行ではない。\n",
    )
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_reverse_full_path_backtick_is_an_escape_hatch(tmp_path: Path) -> None:
    # 別ディレクトリのモジュールを箇条書きで触れたいときはフルパスで書く（`/` を含むので先頭パターンに一致せず、
    # そのプロファイルの置き場に在ることを要求されない）。フルパスの名前は逆向きの抽出対象にならない。
    _profile(tmp_path, "ds", "cv.py")
    _write(tmp_path, "docs/ds.md", "`cv.py` は交差検証。\n")
    _write(tmp_path, "docs/ds-code.md", "- `cv.py` … 交差検証（保存は `src/harness/storage.py` を使う）。\n")
    assert _errors(tmp_path) == []  # フルパス言及 src/harness/storage.py は ds/storage.py の実在を要求しない


@pytest.mark.unit
def test_reverse_scoped_to_the_docs_own_directory(tmp_path: Path) -> None:
    # ds-code.md の箇条書き先頭の `models.py` は src/harness/ds/models.py を指す（中核の models.py ではない）。
    _write(tmp_path, "src/harness/models.py", "")  # 中核には在る
    _profile(tmp_path, "ds", "cv.py")  # だが ds には models.py が無い
    _write(tmp_path, "docs/ds.md", "`cv.py` は交差検証。\n")
    _write(tmp_path, "docs/ds-code.md", "- `models.py` … 学習済みモデルの保存。\n- `cv.py` … 交差検証。\n")
    assert any("src/harness/ds/models.py" in m and "実在しない" in m for m in _errors(tmp_path))


@pytest.mark.integration
def test_declared_modules_extractor_is_not_silently_empty() -> None:
    # 抽出の正規表現が壊れて空を返しても逆向きは緑のままになる（no-op）。実データで非空を固定して黙った破損を防ぐ。
    core_text = (REPO_ROOT / "docs" / "core.md").read_text(encoding="utf-8")
    declared = code_doc_lint._declared_modules(core_text)
    assert declared, "core.md の役割一覧から 1 件も抽出できない＝抽出器が壊れている"
    # core.md の役割一覧は中核の公開モジュールと一致する（順・逆の両向きが締まっている＝どちらも空振りしない）。
    assert set(declared) == set(code_doc_lint._core_modules(REPO_ROOT))


@pytest.mark.integration
def test_role_lists_in_code_docs_stay_extractable() -> None:
    # 逆向きが「書式ドリフトで無言の no-op」になるのを防ぐ（独立レビュー Med）：役割一覧を per-module の行で持つ
    # ドキュメント（core.md と各 <profile>-code.md）から 1 件も抽出できなくなったら、抽出器か doc の書式が
    # 検出範囲（表の行・箇条書きの先頭）から外れた合図。番号付き・太字包みなどへ整形し直すとここで気づける。
    docs_dir = REPO_ROOT / "docs"
    role_docs = [docs_dir / "core.md", *sorted(docs_dir.glob("*-code.md"))]
    for doc in role_docs:
        declared = code_doc_lint._declared_modules(doc.read_text(encoding="utf-8"))
        assert declared, f"{doc.name} の役割一覧から 1 件も抽出できない（書式が逆向きの検出範囲から外れた）"


@pytest.mark.integration
def test_real_repo_has_no_stale_role_rows() -> None:
    # 現リポの全 docs 役割一覧が実在するモジュールだけを挙げている（逆向きの回帰＝以後の消し忘れを止める）。
    stale = [p.message for p in code_doc_lint._reverse_checks(REPO_ROOT)]
    assert stale == [], stale


# --- 免除リストの規約：理由は空でない文字列が必須 ---


@pytest.mark.unit
def test_every_exempt_reason_is_nonempty() -> None:
    for key, reason in code_doc_lint._EXEMPT.items():
        assert isinstance(reason, str) and reason.strip(), f"_EXEMPT[{key!r}] の理由が空"


@pytest.mark.unit
def test_exempt_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile(tmp_path, "ds", "legacy.py")
    _write(tmp_path, "docs/ds.md", "モジュール名は書かない。\n")
    assert any("ds/legacy.py" in m for m in _errors(tmp_path))
    key = "src/harness/ds/legacy.py"
    monkeypatch.setitem(code_doc_lint._EXEMPT, key, "旧経路・撤去予定なので docs から外す（ISS-9999）")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_blank_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(code_doc_lint._EXEMPT, "src/harness/ds/foo.py", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        code_doc_lint.run_checks(tmp_path)


# --- 配線：INVARIANT_CHECKS に載っている ---


@pytest.mark.unit
def test_code_doc_lint_is_wired_into_invariant_checks() -> None:
    from harness import checks

    assert code_doc_lint.run_checks in checks.INVARIANT_CHECKS


# --- 回帰テスト：現リポの全プロファイル＋中核のモジュールが docs で触れられている ---


@pytest.mark.integration
def test_real_repo_profile_modules_are_documented() -> None:
    errors = [p for p in code_doc_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]


@pytest.mark.integration
def test_real_repo_core_modules_are_all_scanned() -> None:
    # 走査対象が「src/harness 直下の公開 .py すべて」であることを、実リポの構成から導いて固定する
    # （glob の書き間違いで対象がゼロ件になっても回帰テストは緑のままになるため、件数の側からも留める）。
    expected = {
        p.name
        for p in (REPO_ROOT / "src" / "harness").glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    }
    assert code_doc_lint._core_modules(REPO_ROOT) == sorted(expected)
    assert expected  # 空集合を「全部載っている」と読み違えない
