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


def test_secrets_exemptions_require_reason() -> None:
    """偽陽性の免除（.gitleaksignore）は理由必須（coverage_lint の _EXEMPT と同型・fail closed）。

    ファイルが無い＝免除ゼロは正常。免除する fingerprint 行には、直前に `# なぜ偽陽性か` のコメントが
    必要。理由の無い免除（黙った例外）は verify で失敗させる。
    """
    path = _ROOT / ".gitleaksignore"
    if not path.is_file():
        return  # 免除ゼロ＝正常（fail closed の対象は「理由なしの免除」）
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
            f".gitleaksignore:{lineno}: 免除 {line!r} に理由が無い。直前の行に"
            " `# なぜ偽陽性か（どのファイルの何のダミー値か）` を書くこと（理由必須・黙った免除は禁止）"
        )
        prev_is_reason = False
