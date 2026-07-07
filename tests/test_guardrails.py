"""エージェント運用ガードレールの配線の常在検査（EP-20 の骨組み＝T-0100）。

ガードレール 1 件＝(a) 執行点（`.claude/settings.json` の deny／pre-commit フック／CI ステップ）＋
(b) 配線が生きているかの常在検査（このファイル。`uv run verify` に接続）という型。実際に止める・
検出する力は執行系（Claude Code の permissions・gitleaks）が担い、ここでは**設定が黙って外れたら
verify が落ちる**こと（fail closed）だけを検査する。

期待値はデータ駆動：ポリシー（T-0100 の受け入れ基準で定めた禁止一覧・必須フック）を下の定数に正本化し、
テストはそれを回すだけ。将来ガードレールを足すときは定数に 1 行足して同じ型をコピーする
（ハードコードの散乱を避ける）。免除（偽陽性の `.gitleaksignore`）は理由必須
（coverage_lint の `_EXEMPT` と同型・理由なしは失敗）。
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]

# --- ポリシーの正本（期待値は受け入れ基準の一覧から導出。実装出力のコピーではない） ---

# 破壊的 git 操作の deny ルール。Claude Code の Bash ルールは接頭辞一致（`:*`＝**語境界つき**末尾ワイルド
# カード）で、フラグの別表記・結合表記ごとに別ルールが必要（公式 permissions 仕様で確認済み）。
# 語境界のため `git clean -f:*` は `git clean -fd`/`-df`/`--force` を捕まえない（`-f` 直後が文字＝境界違反）＝
# 最頻の破壊形 `clean -fd` を素通しするので結合形も明示列挙する（N-2）。フラグ後置（`git push origin --force`）
# 対策は接頭辞一致の外＝hooks/sandbox の領分として T-0101 以降へ回す（settings の接頭辞 deny では覆えない）。
DESTRUCTIVE_GIT_DENY: tuple[str, ...] = (
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(git reset --hard:*)",
    "Bash(git clean -f:*)",
    "Bash(git clean -fd:*)",
    "Bash(git clean -df:*)",
    "Bash(git clean --force:*)",
    "Bash(git branch -D:*)",
)

# 既存の秘密情報 Read 拒否（T-0100 以前からのガード。退行防止のためポリシーに含める）。
SECRET_READ_DENY: tuple[str, ...] = (
    "Read(./.env)",
    "Read(./.env.*)",
    "Read(./secrets/**)",
)

# 秘密情報検出フックの id。ローカル（pre-commit）と CI が**同じ入口**（この 1 つのフック）で回す。
SECRETS_HOOK_ID = "gitleaks"

# フックの走査モードもポリシー：上流既定 `gitleaks git --staged`（ステージ差分のみ）は CI のクリーン
# チェックアウト（差分ゼロ）で何も走査しない空振り＝fail-open。作業ツリー全走査（`gitleaks dir`）に
# 上書きすることが「同一入口が実効を持つ」ための必須条件なので、接頭辞を正本化して entry を検査する
# （entry が消えて上流既定に戻ったら赤くする＝L-014 の vacuous pass を配線テストで守る）。
SECRETS_HOOK_ENTRY_PREFIX = "gitleaks dir"

# 依存脆弱性監査（T-0102）。エージェントが自律的に extra を足す運用では、部分環境の監査は
# 「まだ入れていない extra」の脆弱性を見逃す（部分監査は死角）。よって全部入り（--all-extras）で
# 同期したロック済み環境そのものを pip-audit で監査する。blocking（continue-on-error を付けない）で、
# 免除は .pip-audit-ignore（理由必須の allowlist＝.gitleaksignore・coverage_lint の _EXEMPT と同型）。
AUDIT_JOB_ID = "audit"
AUDIT_SYNC_COMMAND = "uv sync --all-extras"
AUDIT_TOOL = "pip-audit"
AUDIT_IGNORE_FILE = ".pip-audit-ignore"
# 免除エントリとして許す脆弱性 ID の体系（pip-audit の --ignore-vuln が解釈できるもの）。
# ID 以外の文字列（typo）は --ignore-vuln に渡っても何にも一致せず黙って無効になるため、書式で弾く。
AUDIT_VULN_ID_PREFIXES: tuple[str, ...] = ("GHSA-", "CVE-", "PYSEC-", "OSV-")


def test_destructive_git_denied() -> None:
    """settings.json の permissions.deny が破壊的 git 5 種＋秘密情報 Read 3 種を覆っている（fail closed）。"""
    settings = json.loads((_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    for rule in DESTRUCTIVE_GIT_DENY + SECRET_READ_DENY:
        assert rule in deny, (
            f"ガードレール欠落: ルール {rule!r} が .claude/settings.json の permissions.deny に無い。"
            "破壊的 git 操作・秘密情報 Read の deny は黙って外さない。外す/緩める場合はポリシー変更として"
            "このテストの定数（正本）と同時に更新すること（tests/test_guardrails.py）"
        )


def test_secrets_scan_wired() -> None:
    """秘密情報検出がローカル（pre-commit）と CI（同フック id）の同一入口で配線されている。"""
    pre_commit = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [hook for repo in pre_commit["repos"] for hook in repo["hooks"]]
    hook = next((h for h in hooks if h["id"] == SECRETS_HOOK_ID), None)
    assert hook is not None, (
        f"秘密情報検出フック '{SECRETS_HOOK_ID}' が .pre-commit-config.yaml に無い。"
        "コミットに鍵を書く経路が無防備になる。フックを戻すこと（T-0100 の執行点）"
    )
    # 走査モードの検査（B-1）：entry が全走査（dir モード）に上書きされていること。上流既定
    # `gitleaks git --staged` に戻ると CI のクリーンチェックアウトで空振り（Passed）＝fail-open が復活する。
    entry = hook.get("entry", "")
    assert entry.startswith(SECRETS_HOOK_ENTRY_PREFIX), (
        f"gitleaks フックの entry が {SECRETS_HOOK_ENTRY_PREFIX!r} で始まっていない（実際: {entry!r}）。"
        "上流既定の `gitleaks git --staged` はステージ差分だけを走査し、CI のクリーンチェックアウト"
        "（差分ゼロ）では何も走査しない空振り＝fail-open になる。作業ツリー全走査（dir モード）に上書きすること"
    )
    ci = yaml.safe_load((_ROOT / ".github" / "workflows" / "ci.yaml").read_text(encoding="utf-8"))
    runs = [step.get("run", "") for job in ci["jobs"].values() for step in job.get("steps", [])]
    secrets_runs = [run for run in runs if "pre-commit run" in run and SECRETS_HOOK_ID in run]
    assert secrets_runs, (
        f"CI（.github/workflows/ci.yaml）が秘密情報フック '{SECRETS_HOOK_ID}' を pre-commit 経由で"
        "回していない。ローカルと CI は同じ入口（`uvx pre-commit run <hook-id> --all-files`）を使う。"
        "CI だけ別ツールにしない"
    )
    # `--all-files` が無いと pre-commit は変更ファイル（CI では通常ゼロ）だけを対象にして no-op になり得る。
    assert any("--all-files" in run for run in secrets_runs), (
        f"CI の秘密情報スキャンに `--all-files` が無い（実際: {secrets_runs!r}）。"
        "`pre-commit run gitleaks` 単体は変更ファイルが無いと何も走査しない空振りになるため、"
        "CI では `--all-files` を付けて全走査する"
    )


def _exemption_entries_with_reason_check(path: Path, reason_hint: str) -> list[str]:
    """免除 allowlist（1 行 1 エントリ・`#` コメント）の各エントリに理由コメントが直前にあることを検査する。

    .gitleaksignore と .pip-audit-ignore の共通の型（coverage_lint の _EXEMPT と同型・fail closed）。
    理由の無い免除（黙った例外）は verify で失敗させる。検査を通ったエントリ一覧を返す。
    """
    entries: list[str] = []
    prev_is_reason = False
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            prev_is_reason = False
            continue
        if line.startswith("#"):
            prev_is_reason = bool(line.lstrip("#").strip())
            continue
        assert prev_is_reason, (
            f"{path.name}:{lineno}: 免除 {line!r} に理由が無い。直前の行に"
            f" `# {reason_hint}` を書くこと（理由必須・黙った免除は禁止）"
        )
        prev_is_reason = False
        entries.append(line)
    return entries


def test_secrets_exemptions_require_reason() -> None:
    """偽陽性の免除（.gitleaksignore）は理由必須（coverage_lint の _EXEMPT と同型・fail closed）。

    ファイルが無い＝免除ゼロは正常。免除する fingerprint 行には、直前に `# なぜ偽陽性か` のコメントが
    必要。理由の無い免除（黙った例外）は verify で失敗させる。
    """
    path = _ROOT / ".gitleaksignore"
    if not path.is_file():
        return  # 免除ゼロ＝正常（fail closed の対象は「理由なしの免除」）
    _exemption_entries_with_reason_check(path, "なぜ偽陽性か（どのファイルの何のダミー値か）")


def test_ci_has_dependency_audit_job() -> None:
    """CI に依存脆弱性監査の独立ジョブがあり、全部入り同期→pip-audit・blocking で配線されている。

    期待値はポリシー定数（AUDIT_*）から導出：(1) `audit` ジョブが実在、(2) `uv sync --all-extras`
    （部分監査は死角）と pip-audit の実行を含む、(3) continue-on-error が付いていない（blocking の退行防止）、
    (4) 免除 allowlist（.pip-audit-ignore）が監査コマンドに配線され、ファイルが実在する（孤児化防止）。
    """
    ci = yaml.safe_load((_ROOT / ".github" / "workflows" / "ci.yaml").read_text(encoding="utf-8"))
    job = ci["jobs"].get(AUDIT_JOB_ID)
    assert job is not None, (
        f"CI（.github/workflows/ci.yaml）に依存脆弱性監査ジョブ '{AUDIT_JOB_ID}' が無い。"
        "エージェントが自律的に依存（extra）を足す運用のサプライチェーン監査が無防備になる。"
        "ジョブを戻すこと（T-0102 の執行点）"
    )
    runs = [step.get("run", "") for step in job["steps"]]
    assert any(AUDIT_SYNC_COMMAND in run for run in runs), (
        f"audit ジョブが '{AUDIT_SYNC_COMMAND}' で同期していない（実際: {runs!r}）。"
        "部分環境の監査は「入れていない extra」の脆弱性を見逃す死角になる。全部入りで同期して監査すること"
    )
    audit_runs = [run for run in runs if AUDIT_TOOL in run]
    assert audit_runs, f"audit ジョブが {AUDIT_TOOL} を実行していない（実際: {runs!r}）。同期だけでは監査にならない"
    # continue-on-error の穴塞ぎ：非ゼロ終了を shell 側で握り潰す（`|| true`／末尾 `exit 0`）と blocking が
    # 有名無実化する。将来「とりあえず CI を通す」ための握り潰し退行を verify で止める（NIT#3）。
    for run in runs:
        assert "|| true" not in run and "exit 0" not in run, (
            f"audit ジョブの run に握り潰し（`|| true` / `exit 0`）がある（実際: {run!r}）。"
            "監査コマンドの非ゼロ終了を握り潰すと blocking が無効化する。免除は .pip-audit-ignore"
            "（理由必須）だけで行うこと"
        )
    # blocking の退行防止：ジョブにもステップにも continue-on-error を置かない（true への緩和も、
    # 式（${{ ... }}）で条件化する抜け道も、キーの不在で一律に禁止する＝fail closed）。
    assert "continue-on-error" not in job, (
        "audit ジョブに continue-on-error が付いている。監査は blocking（脆弱性で CI 赤）がポリシー。"
        "緩めたい場合は個別の脆弱性 ID を .pip-audit-ignore に理由つきで載せること（ジョブ全体は緩めない）"
    )
    assert all("continue-on-error" not in step for step in job["steps"]), (
        "audit ジョブのステップに continue-on-error が付いている。監査は blocking がポリシー。"
        "免除は .pip-audit-ignore（理由必須）だけで行うこと"
    )
    assert any(AUDIT_IGNORE_FILE in run for run in audit_runs), (
        f"監査コマンドが免除 allowlist '{AUDIT_IGNORE_FILE}' を読んでいない（実際: {audit_runs!r}）。"
        "allowlist が配線されていないと、免除の追加が黙って無効になる（孤児ファイル）"
    )
    assert (_ROOT / AUDIT_IGNORE_FILE).is_file(), (
        f"免除 allowlist '{AUDIT_IGNORE_FILE}' が無い。CI の監査コマンドが参照するため、"
        "空（コメントのみ＝免除ゼロ）でもファイル自体は置くこと"
    )


def test_audit_exemptions_require_reason() -> None:
    """依存監査の免除（.pip-audit-ignore）は理由必須＋脆弱性 ID 書式（fail closed）。

    各エントリの直前に理由コメントが必要（.gitleaksignore と同型）。加えてエントリは pip-audit の
    --ignore-vuln が解釈できる ID 体系（GHSA-/CVE-/PYSEC-/OSV-）であること：ID 以外の文字列（typo）は
    何にも一致せず黙って無効になるため、書式の段階で弾く。
    """
    path = _ROOT / AUDIT_IGNORE_FILE
    assert path.is_file(), (
        f"'{AUDIT_IGNORE_FILE}' が無い（CI の監査コマンドが参照する前提のファイル）。"
        "免除ゼロでもコメントのみのファイルとして置くこと（test_ci_has_dependency_audit_job と同じポリシー）"
    )
    entries = _exemption_entries_with_reason_check(
        path, "なぜ免除するか（誤陽性 or 修正待ちの根拠）と見直し期限（YYYY-MM）"
    )
    for entry in entries:
        assert entry.startswith(AUDIT_VULN_ID_PREFIXES), (
            f"{AUDIT_IGNORE_FILE}: 免除 {entry!r} が脆弱性 ID の書式（{AUDIT_VULN_ID_PREFIXES} のいずれかで"
            "始まる）でない。typo の免除は --ignore-vuln に渡っても何にも一致せず黙って無効になるため、"
            "書式で弾く（fail closed）"
        )


def test_gitleaks_reason_check_rejects_reasonless_second_entry(tmp_path: Path) -> None:
    """コメント無しの 2 連続エントリの 2 件目は理由なしで REJECT（fail-closed の厳密さをロック）。

    共通ヘルパ `_exemption_entries_with_reason_check` は各エントリを通すたび理由フラグを消費するため、
    間にコメントが無い 2 件目は「直前が理由コメント」を満たさず AssertionError になる（T-0100 と同一の
    厳密さ）。実ファイルを見る既存テストは単一エントリしか通らずこの緩みを検出できないので、合成入力で
    固定する。期待値は構成から導出：1 件目に理由あり・2 件目に理由なし → 2 件目（fingerprint-bbbb）で赤。
    """
    path = tmp_path / ".gitleaksignore"
    path.write_text("# なぜ偽陽性か: ダミー1\nfingerprint-aaaa\nfingerprint-bbbb\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="fingerprint-bbbb"):
        _exemption_entries_with_reason_check(path, "なぜ偽陽性か")
    # 対照：2 件目にも直前理由を付ければ両方通り、エントリ 2 件が順に返る（構成どおり）。
    path.write_text("# r1: ダミー1\nfingerprint-aaaa\n# r2: ダミー2\nfingerprint-bbbb\n", encoding="utf-8")
    assert _exemption_entries_with_reason_check(path, "なぜ偽陽性か") == [
        "fingerprint-aaaa",
        "fingerprint-bbbb",
    ]


def test_audit_reason_check_rejects_reasonless_second_entry(tmp_path: Path) -> None:
    """依存監査側でも同型：コメント無しの 2 連続 ID の 2 件目は理由なしで REJECT（fail-closed をロック）。

    期待値は構成から導出：1 件目に理由あり・2 件目に理由なし → 2 件目（CVE-2099-0002）で赤。対照として
    各 ID に直前理由を付ければ両方通り、ID が順に返る。
    """
    path = tmp_path / AUDIT_IGNORE_FILE
    path.write_text("# 修正待ち 2026-09\nCVE-2099-0001\nCVE-2099-0002\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="CVE-2099-0002"):
        _exemption_entries_with_reason_check(path, "なぜ免除するか")
    path.write_text("# r1 2026-09\nCVE-2099-0001\n# r2 2026-09\nCVE-2099-0002\n", encoding="utf-8")
    assert _exemption_entries_with_reason_check(path, "なぜ免除するか") == [
        "CVE-2099-0001",
        "CVE-2099-0002",
    ]


def test_core_docs_link_profile_entrypoints() -> None:
    """AGENTS.md のコマンド節がプロファイル CLI 入口（`uv run <cmd>`）への導線を持つ（T-0103）。

    期待トークンは `pyproject.toml` の `[project.scripts]` から導出する：entry point が core モジュール
    （`harness.cli`）以外を指すスクリプト名＝プロファイル CLI（現状 data・serve・agent）。3 トークンの
    ハードコードでなく scripts から導くので、プロファイル CLI の増減にそのまま追従する（二重実装なし。
    coverage_lint は「コマンド→スキル/docs の到達可能性」を守り、ここは「最初に読む正本 AGENTS.md からの
    見つけやすさ」という別の関心を守る）。
    """
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts: dict[str, str] = pyproject["project"]["scripts"]
    profile_cmds = sorted(name for name, entry in scripts.items() if not entry.startswith("harness.cli:"))
    assert profile_cmds, "[project.scripts] にプロファイル CLI が無い（構成が変わったらこの検査を見直す）"
    agents_text = (_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    missing = [cmd for cmd in profile_cmds if f"uv run {cmd}" not in agents_text]
    assert not missing, f"AGENTS.md にプロファイル入口の導線が無い: {missing}"
