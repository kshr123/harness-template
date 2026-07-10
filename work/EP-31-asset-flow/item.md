---
id: EP-31
kind: epic
status: in-progress
plan: detailed
requirements: [REQ-003]
depends_on: [EP-27]
created: 2026-07-10
---
# EP-31 複製できる状態を保つ（恒久資産 → 一時単位の参照を断つ）

## 目的
この基盤の最上位の目的は「案件を重ねるほど強くなる」こと。そのためには**配れる**（テンプレートとして複製できる）
必要がある。ところが手順どおりに複製すると、緑になる状態が存在しない（デッドロック）。それを直す。

## 実測したデッドロック（再現手順と出力）
`docs/template-copy.md` は複製時に前案件の `work/` と `issues/` を消せと指示する。手順どおり空にすると：

再現（clone → work/ と issues/ を空 → `uv run verify`）:

```
git clone . /tmp/repro && cd /tmp/repro
uv sync --all-extras
git rm -r work && git rm issues/ISS-*.md
uv run verify
```

結果（doclint の死にリンク検査が 8 件で error）:

```
✗ docs/core.md: 'ISS-0015' の置き場 'issues' が存在しない
✗ docs/learnings.md: 'ISS-0010' の置き場 'issues' が存在しない
✗ src/harness/code_doc_lint.py: 'ISS-0015' の置き場 'issues' が存在しない
✗ src/harness/conventions.py: 'ISS-0002' の置き場 'issues' が存在しない
✗ src/harness/coverage_lint.py: 'ISS-0014' の置き場 'issues' が存在しない
✗ src/harness/doclint.py: 'ISS-0001' の置き場 'issues' が存在しない
✗ src/harness/doclint.py: 'ISS-0003' の置き場 'issues' が存在しない
✗ src/harness/ds/experiment.py: 'ISS-0007' の置き場 'issues' が存在しない
```

**逃げ場が無い**：課題を残すと今度は pm 検査（resolved 済み issue の `promoted_to` が、消した `work/` の
作業単位を指す）が落ちる。緑にする唯一の道は「触らない」はずの `src/harness/` から `ISS-…` 参照を剥がすこと。

さらに `templates/experiment/train.py` は `work/EP-06-…` / `work/E-0001` を参照していたが、`doc_source_lint` は
`README.md`・`AGENTS.md`・`docs/*.md` しか見ていなかったので捕まえられなかった（走査範囲の穴）。

## 原則（AGENTS.md に既にある。適用範囲が足りていなかっただけ）
**複製後も残る資産は一時的な単位（`work/…`・`issues/…`）を設計の根拠に参照しない。** 根拠は本文の説明として
書く（複製すると `work/` と `issues/` は消える／置き換わるので）。同じ原則を `ISS-…` にも、`src/`・`tests/`・
`templates/`・`.claude/skills/` にも広げる。**新しい機構ではなく、既存の封鎖（`doc_source_lint`）の穴埋め。**

## タスク
- **T-0190**：参照を断つ（`src/harness/**`・`docs/**` から `ISS-…`・`work/…` の設計根拠参照を剥がし、
  経緯は本文の説明に書き直す）。`issues/` のファイル自体は消さない。
- **T-0181**：`doc_source_lint` の走査対象を `templates/**`・`src/harness/**`・`tests/**`・`.claude/skills/**` へ
  広げ、`ISS-…` 参照も `work/…` と同じく error にする。`templates/experiment/train.py` を同じタスクで直す。
