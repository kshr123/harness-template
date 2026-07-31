---
id: EP-54
kind: epic
status: in-progress
plan: detailed
requirements: []
depends_on: []
---
# EP-54 検査の共有基盤（lintkit）＝理想アーキテクチャへ

EP-53 に続く「verify の脱・accretion」の本丸。fable の全体設計に基づく。各 lint が同じ土台（対象集合・
免除表・ID 文法・ast 解析・GH Actions 走査）を少しずつ違う方言で重複して持っていた（テストの約 3 割が
検査機構のテスト）。共有基盤 `src/harness/lintkit/` を **1 度だけテスト**し、各検査を「固有の判定だけ」に縮める
＝新しい検査の限界費用を下げる（＝compounding）。実行時間は非目標（不変検査は 2.3 秒）。

**DSL 化はしない**（判定が異種すぎて機構だけ増える）。プロファイル境界（`Profile.invariant_checks`）は不変＝
プロファイルは lintkit を import してよい（profile→core 方向）。`Rule.from_callable` で既存の `InvariantCheck`
（`fn(root)`）をそのまま包める。

## フェーズ（各 1 まとまり・verify 緑を保つ・旧テストを等価スイートとして残し、移行時にルールごとに変異で赤を証明・2 モジュールを 1 度に移さない）
- T-0302 **P0**：`lintkit`（Corpus・Exemptions・ids・Rule/run）＋自前テスト。未結線。
- T-0303 **P1**：4 か所の免除検証（`_validated_exempt`）を lintkit へ機械置換（旧テスト無改変＝挙動不変の証明）。
  語境界・`relative_to().as_posix()` の集約は P3（doclint＋doc_source＋code_doc をまとめて移すとき）に回す。
- P2：`profile_doc_lint` を `code_doc_lint` へ統合（16→15。存在検査の重複を解消）。
- P3：`doclint`＋`doc_source_lint` を共有 Corpus/ids の上へ（重複テストを collapse）。
- P4：`conventions` を 5 個の小ルールへ。
- P5：`lintkit.workflows` を `ci_lint` から抽出し `schedule_lint` を載せ替え。
- P6：agent `lint` を AgentSpec バリデータ＋薄いローダへ。
- P7：`doc_sync`→`uv run verify --list` は要判断（人が読める表を失うため既定は保持）。

## 含めない
- Rule-combinator DSL／pm・issues・deploy_lint・wbs_lint の枠組み化／coverage・boundary の構造化／
  変異確認の meta-meta 自動化（＝取り除きたい機構を再増殖させる）。
- `test_verification_mechanism`・`_verify_checks_config`（起動前の関門）は触らない。
