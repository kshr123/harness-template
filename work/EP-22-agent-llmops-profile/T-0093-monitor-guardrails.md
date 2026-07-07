---
id: T-0093
kind: task
status: todo
created: 2026-07-07
depends_on: [T-0091]
verified_by: [tests/test_agent_monitor.py::test_monitor_rates_and_cost_from_constructed_logs]
---
# T-0093 監視（agent monitor・門番にしない）＋ガードレール（guardrails）

## 狙い（実行ログ→運用の目・入出力の縮退）
T-0091 で 1 実行の JSONL 契約（`AGENT_LOG_FIELDS`）を作った。運用側はこの行だけを読み、**品質の代理（拒否/
打ち切り率）・コスト（トークン/ターン）・ツール使用**を人が読む数字で出す（`ds/monitor` と同じ規律＝**門番に
しない**・壊れ行は警告して読み飛ばす・消費するキーだけ検証・寛容に読む）。加えて入出力の**ガードレール**
（出力の JSON schema 検証＋入力の PII 正規表現スタブ）を Protocol で足す（検出モデルは委譲）。

## 設計判断（プロファイル境界と core の軽さを両立＝psi は流用しない）
- **`eda.psi` は流用しない**（当初 outline から変更・理由を記録）。理由：(1) agent プロファイルは `ds` を import
  できない（DEC-0004）。(2) `eda.psi` は numpy/polars 依存だが **core は stdlib 中心で numpy を 1 つも持たない**
  （実測）＝psi を core に引き上げると core の軽さが壊れる。(3) psi は「基準の特徴分布」との比較＝**特徴は ds の
  領域**で、agent の実行ログに基準特徴表は無い。agent 運用の効く信号は**拒否率とコスト**＝基準分布の要らない
  素の集計。→ monitor は **stdlib のみ**（numpy/polars/ds 非依存＝軽い）で集計する。数値系列のドリフト（出力長
  など）が要るなら、そのとき psi を core へ引き上げる（DEC-0012＝一般性で判断・3 個目の消費が出たら）。soon。

## 受け入れ基準
### `src/harness/agent/monitor.py`（新規・純関数・stdlib のみ・門番にしない）
- `read_agent_logs(files: Sequence[Path], *, since: date | None = None) -> AgentLogs`：JSONL を寛容に読む。
  壊れ行・契約違反（consume するキーが無い/型違い）は `warnings.warn` して読み飛ばし `n_skipped` に数える
  （監視が盲目になるより縮退＝`ds/monitor` と同作法）。消費するキーだけ検証：`time`(str・--since 用)・
  `stop_reason`(str)・`usage`(dict: input_tokens/output_tokens int)・`turns`(int)・`tools_used`(list[str])。
  使わないキー（request_id 等）は見ない。`--since`（境界日を含む・YYYY-MM-DD）で古い行を落とす。
- `monitor(logs: AgentLogs) -> AgentMonitorReport`（frozen dataclass・`to_dict()` で YAML 化）：
  - `n_rows` / `n_skipped`。
  - `stop_reason` 分布（`collections.Counter`）＋率：`non_end_turn_rate`（＝1−end_turn 率＝失敗/打ち切りの代理）・
    `max_turns_rate`（ツール往復の上限打ち切り率）。0 行なら率は 0.0（0 割を作らない）。
  - コスト要約：`input_tokens`・`output_tokens`・`turns` の分位（p05/p25/p50/p75/p95）を stdlib で算出
    （`statistics.quantiles` かニアレストランク＝方式を docstring に明記・期待値はテスト入力の構成から導出）。
  - `tools_used` の頻度（Counter・呼んだ回数）。
  - 帯（**門番でない**・目安の離散化）：`rate_band(value) -> "安定"|"要注意"|"大変化"`（watch/alert のしきいは
    定数で docstring に「目安・exit code に載せない」と明記）。`non_end_turn_rate` を帯で言葉にする。
- 監視はネットワーク・ファイル書き込みをしない（読むだけ）。exit code に判定を載せない（CLI 側も exit 0）。

### `src/harness/agent/guardrails.py`（新規・stdlib のみ・新規依存を足さない）
- `GuardResult`（frozen）：`ok: bool`・`reason: str`・`matches: tuple[str, ...]`（PII 抽出片＝伏字のヒント）。
- `Guard` Protocol：`def check(self, text: str) -> GuardResult`。
- `PiiRegexGuard`（入力ガードのスタブ）：email＋電話番号の正規表現で検出（見つかれば `ok=False`＋`matches`）。
  **スタブである旨と、実際の PII 検出はモデルへ委譲する旨を docstring に明記**（正規表現スタブ・DEC-0009 の作法）。
- `validate_output_schema(output: str, schema: Mapping[str, Any]) -> GuardResult`：出力を JSON として解釈し
  （非 JSON は `ok=False`）、**JSON Schema の最小部分集合**（`type`＝object/array/string/number/boolean・
  `required`・`properties` の型）を検証する。`AgentSpec.output_schema`（Mapping|None）に対応。
  jsonschema は base 依存に無い（推移的のみ）ため**依存しない**＝最小部分集合の自前検証にとどめ、
  完全検証は jsonschema へ委譲する旨を docstring に書く（PII スタブと同じ「入口だけ・委譲点を明示」）。
- Registry 化はしない（YAGNI・2 実装目で昇格＝item.md/DEC-0012）。

### `src/harness/agent/cli.py`：`agent monitor` コマンド（新規・遅延 import・門番でない）
- 引数：`--log`（glob・既定 `artifacts/agent/runs/**/*.jsonl`）・`--since`（YYYY-MM-DD）・
  `--file-issue`（帯が要注意/大変化のとき課題を冪等起票）。
- 既定は `monitor(...).to_dict()` を YAML で出力し **exit 0**（agent には基準表が無い＝唯一の門番も無い）。
- `--file-issue`：`non_end_turn_rate` の帯が「要注意」以上のとき課題を起票する。**冪等**＝決定的タイトル
  `[agent-monitor] non_end_turn_rate <帯>` を作り、既存の open 課題（`issues.load_issues`）に同タイトルが
  あれば起票しない（既存 ID を表示）。無ければ `issues.local_dir`/`next_id` で 1 件作る（`issue new` と同作法・
  github: backend は起票しない旨を表示＝`issue new` と同じ）。二度叩いても 1 件（テストで固定）。
- **導線必須**（coverage_lint が `agent monitor` を強制）：docs/agent.md とスキルに使い方を書く（下記）。

### 導線・ドキュメント（coverage_lint＝missing link を止める・DEC-0016）
- `docs/agent.md`：監視の節（`agent monitor`・門番でない・拒否率/コスト/ツール・`--file-issue` 冪等）＋
  ガードレールの節（Protocol・PII 正規表現スタブ・出力 schema 最小検証・委譲点）。
- `.claude/skills/agent/SKILL.md`：監視とガードレールの 1〜2 行（`agent monitor` の呼び方＋guardrails 部品）。

## 触ってよいファイル
`src/harness/agent/monitor.py`（新規）・`src/harness/agent/guardrails.py`（新規）・`src/harness/agent/cli.py`
（`monitor` コマンド追加のみ）・`docs/agent.md`・`.claude/skills/agent/SKILL.md`・
`tests/{test_agent_monitor.py,test_agent_guardrails.py}`（新規）。`ds/**`・`serve/**`・`runtime.py` の契約は
**変更しない**（`AGENT_LOG_FIELDS` は読むだけ）。core（`issues.py` 等）は import して使うだけ・変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須・無ネットワーク）
- `test_agent_monitor.py::test_monitor_rates_and_cost_from_constructed_logs`（**unit**）：end_turn と max_turns を
  既知の比で混ぜ・トークン/ターン/ツールを既知に構成した行列から、`non_end_turn_rate`・`max_turns_rate`・分位・
  ツール頻度が構成どおりになる（期待値は入力の作り方から説明できる＝金メッキ禁止）。
- 壊れ行の寛容（**unit**）：契約違反行（usage 欠け等）は `n_skipped` に数え warn する・他の行は生きる。
- `--since` 境界（**unit**）：境界日を含み、より古い行を落とす。
- guardrails（**unit**）：PII 正規表現が email/電話を検出（構成した文字列）・clean text は ok。出力 schema＝
  正しい JSON かつ schema 適合は ok・required 欠け/型違い/非 JSON は `ok=False`（構成から導出）。
- `agent monitor` CLI（**integration**）：一時 root に JSONL を置き、YAML に期待キーが出る（exit 0）。
  `--file-issue` を 2 連続で叩いても課題は 1 件（冪等）＝同タイトルの open を再作成しない。
- coverage_lint 緑（`agent monitor` の導線がスキル/docs に在る）。`uv run verify` 全体緑・`verified_by` 実在。

## この骨組みでやらないこと（soon/later・理由つき）
- **数値系列の psi ドリフト**（出力長など）：psi を core へ引き上げるか agent 内複製が要る＝上の設計判断のとおり
  3 個目の消費が出たら DEC-0012 で core 昇格（今は拒否率/コストで足りる）。soon。
- **品質スコアの監視**：judge の点は実行ログ契約に無い（eval の関心）＝ログに載せるなら別 DEC。later。
- **guards の Registry 化・実 PII 検出モデル・完全 JSON Schema**：2 実装目・必要時に即（委譲点は docstring に明示）。
- OpenTelemetry 実エクスポート・SSE・レートリミッタは item.md の later のまま。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：monitor が門番でない＝exit 0 で判定を載せない・壊れ行で盲目にならず縮退する・
率/分位/ツール頻度が構成から導け金メッキでない・`--file-issue` が冪等＝同タイトル open を再作成しない・
guardrails が非 JSON/required 欠け/型違い/PII を取りこぼさない＝変異で検出・agent は ds/numpy/polars を
import しない＝軽さと境界の維持・ネットワーク 0）
