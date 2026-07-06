"""conventions lint（テスト規約の機械検査・ISS-0002）のテスト。

期待値はすべて一時ディレクトリに置くファイルの構成（どんなコードを書いたか）から導く。
skip/xfail の ISS 参照はヘルパ（testing.skips_without_iss）の単体テストで確かめる＝実テストに実 skip を足さない。
最後の 1 本は現リポに対する回帰の番人（グローバル種なし・work の code に --test あり）。乱数は使わない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import conventions
from harness.testing import skips_without_iss

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in conventions.run_checks(root) if p.level == "error"]


# --- グローバル種の検出 ---


def test_np_random_seed_call_is_error_with_file_and_line(tmp_path: Path) -> None:
    # 2 行目に呼び出しを書いたので、エラーは「ファイル:2」を含むはず（構成から導出）。
    _write(tmp_path, "src/mod.py", "import numpy as np\nnp.random.seed(0)\n")
    errors = _errors(tmp_path)
    assert len(errors) == 1
    assert "src/mod.py:2" in errors[0]


def test_numpy_and_stdlib_random_seed_are_error(tmp_path: Path) -> None:
    # tests/ も走査対象。numpy.random.seed と random.seed の 2 呼び出し＝error 2 件。
    _write(tmp_path, "tests/t.py", "import numpy\nimport random\nnumpy.random.seed(1)\nrandom.seed(2)\n")
    errors = _errors(tmp_path)
    assert len(errors) == 2
    assert any("tests/t.py:3" in m for m in errors)
    assert any("tests/t.py:4" in m for m in errors)


def test_default_rng_and_explicit_seed_args_are_ok(tmp_path: Path) -> None:
    # 明示引数（seed=/random_state=）と default_rng は規約どおり＝関数名 seed の呼び出しだけを検出する。
    _write(
        tmp_path,
        "src/ok.py",
        "import numpy as np\nrng = np.random.default_rng(0)\n\n\ndef fit(random_state: int, seed: int) -> None:\n"
        "    pass\n\n\nfit(random_state=0, seed=0)\n",
    )
    assert _errors(tmp_path) == []


def test_seed_in_string_and_comment_is_not_detected(tmp_path: Path) -> None:
    # ast 走査なので文字列・コメント中の記述は呼び出しにならない＝検出しない。
    _write(tmp_path, "src/doc.py", '# np.random.seed(0) は禁止\nrule = "np.random.seed(0)"\n')
    assert _errors(tmp_path) == []


def test_work_code_is_scanned_for_global_seed(tmp_path: Path) -> None:
    # work/**/code/*.py も走査対象（argparse を使わないので --test の error は出ない＝seed の 1 件だけ）。
    _write(tmp_path, "work/EP-01/E-0001/code/util.py", "import random\nrandom.seed(1)\n")
    errors = _errors(tmp_path)
    assert len(errors) == 1
    assert "work/EP-01/E-0001/code/util.py:2" in errors[0]


# --- 実験スクリプトの --test 必須 ---

_ARGPARSE_WITH_TEST = (
    "import argparse\n\nparser = argparse.ArgumentParser()\n"
    'parser.add_argument("--test", action="store_true")\nparser.parse_args()\n'
)
_ARGPARSE_WITHOUT_TEST = (
    'import argparse\n\nparser = argparse.ArgumentParser()\nparser.add_argument("--variant")\nparser.parse_args()\n'
)


def test_work_script_with_test_flag_is_ok(tmp_path: Path) -> None:
    _write(tmp_path, "work/EP-01/E-0001/code/train.py", _ARGPARSE_WITH_TEST)
    assert _errors(tmp_path) == []


def test_work_script_without_test_flag_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "work/EP-01/E-0001/code/train.py", _ARGPARSE_WITHOUT_TEST)
    errors = _errors(tmp_path)
    assert len(errors) == 1
    assert "work/EP-01/E-0001/code/train.py" in errors[0]
    assert "--test" in errors[0]


def test_work_module_without_argparse_is_not_required_to_have_test(tmp_path: Path) -> None:
    # argparse を使わない .py（実験フォルダ内の部品モジュール）は実行入口でない＝対象外（保守的判定）。
    _write(tmp_path, "work/EP-01/E-0001/code/helpers.py", "def add(a: int, b: int) -> int:\n    return a + b\n")
    assert _errors(tmp_path) == []


def test_argparse_cli_outside_work_is_not_required_to_have_test(tmp_path: Path) -> None:
    # --test 規約は work の code だけに課す（src/ の CLI には課さない）。
    _write(tmp_path, "src/cli.py", _ARGPARSE_WITHOUT_TEST)
    assert _errors(tmp_path) == []


# --- skip/xfail の ISS 参照（ヘルパの単体テスト・実 skip は足さない） ---


def test_xfail_with_iss_reference_is_ok() -> None:
    assert skips_without_iss([("t.py::test_a", [("xfail", "ISS-1234 のため")])]) == []


def test_skip_without_iss_reference_is_detected() -> None:
    assert skips_without_iss([("t.py::test_b", [("skip", "未実装")])]) == ["t.py::test_b"]


def test_skip_with_empty_reason_is_detected() -> None:
    # reason 無し（空文字）も参照無しとして返す。
    assert skips_without_iss([("t.py::test_c", [("skip", "")])]) == ["t.py::test_c"]


def test_skipif_is_covered_and_other_markers_are_ignored() -> None:
    # skipif も対象。unit/slow などのピラミッド・フラグの目印は reason を見ない（対象外）。
    items = [
        ("t.py::test_d", [("skipif", "win では動かない")]),
        ("t.py::test_e", [("unit", ""), ("slow", "")]),
        ("t.py::test_f", [("skipif", "win では動かない（ISS-0042）")]),
    ]
    assert skips_without_iss(items) == ["t.py::test_d"]


# --- 現リポの回帰の番人 ---


def test_current_repo_has_no_convention_errors() -> None:
    # 既存はグローバル種なし・skip なし・train.py に --test あり。落ちたら本物の違反（このテストは直さない）。
    assert _errors(REPO_ROOT) == []


# --- レビュー指摘の穴（T-0069 独立レビュー）を塞いだ回帰テスト ---


def test_short_flag_before_test_is_not_false_positive(tmp_path: Path) -> None:
    # add_argument("-t", "--test") は準拠なのに、第1引数だけ見ると誤検出する（I-1）。位置引数のどれかが --test なら OK。
    script = "import argparse\np = argparse.ArgumentParser()\np.add_argument('-t', '--test', action='store_true')\n"
    _write(tmp_path, "work/EP/E/code/train.py", script)
    assert _errors(tmp_path) == []


def test_global_seed_in_code_subpackage_is_scanned(tmp_path: Path) -> None:
    # work/**/code の直下でなく配下のパッケージ（code/pkg/mod.py）でもグローバル種を検出する（I-3）。
    _write(tmp_path, "work/EP/E/code/pkg/mod.py", "import random\nrandom.seed(1)\n")
    errors = _errors(tmp_path)
    assert len(errors) == 1
    assert "code/pkg/mod.py:2" in errors[0]


def test_imperative_skip_without_iss_is_error(tmp_path: Path) -> None:
    # 命令形 pytest.skip("理由") はマーカー検査（conftest）を素通りする → 静的検査で ISS 参照を要求する（I-2）。
    _write(tmp_path, "tests/test_x.py", "import pytest\ndef test_a():\n    pytest.skip('未実装')\n")
    errors = _errors(tmp_path)
    assert len(errors) == 1 and "ISS" in errors[0]


def test_imperative_skip_with_iss_and_importorskip_are_ok(tmp_path: Path) -> None:
    # ISS 参照つき pytest.skip は OK。pytest.importorskip（optional 依存の入口）は対象外（ISS 不要）。
    _write(
        tmp_path,
        "tests/test_y.py",
        "import pytest\npytest.importorskip('skops')\ndef test_a():\n    pytest.skip('ISS-0002 で保留中')\n",
    )
    assert _errors(tmp_path) == []


def test_from_import_seed_call_is_error(tmp_path: Path) -> None:
    # from numpy.random import seed; seed(0) は禁止関数そのものの直接呼び出し（m-1）。属性チェーン以外も捕まえる。
    _write(tmp_path, "src/mod.py", "from numpy.random import seed\nseed(0)\n")
    errors = _errors(tmp_path)
    assert len(errors) == 1 and "src/mod.py:2" in errors[0]
