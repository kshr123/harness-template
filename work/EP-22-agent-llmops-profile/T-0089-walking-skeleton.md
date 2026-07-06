---
id: T-0089
kind: task
status: done
title: harness.agent 歩く骨組み（宣言→dummy→採点→合否→検証が一巡・ネットワーク0）
created: 2026-07-06
depends_on: [T-0084]
verified_by: [tests/test_agent_e2e.py::test_agent_eval_smoke_no_network]
---
# T-0089 harness.agent 歩く骨組み

## 狙い（端まで通る最小＝method.md A 節）
入力（`AgentSpec`）→処理（dummy provider が応答）→採点（`AGENT_METRICS` の exact_match）→合否（`eval.passes`）
→検証（`--test` スモーク＝`uv run verify` に接続）を **1 本通す**。以降のタスク（昇格・ツール往復・実プロバイダ・監視）は
この緑を保ったまま各部を差し替える。**核の制約＝テスト中にネットワークを一切叩かない**（dummy provider のみ）。

## 受け入れ基準（新規 `src/harness/agent/`・軽 import 規約＝DEC-0013）
- **`spec.py`**：`AgentSpec`（`@dataclass(frozen=True, kw_only=True)`、または pydantic で `extra="forbid"`）。
  フィールド：`name: str`／`provider: str`（PROVIDERS の kind）／`model: str`／`system_prompt: str`／
  `tools: tuple[str,...]=()`／`effort: Literal["low","medium","high","xhigh","max"]="medium"`／`max_turns: int=8`／
  `output_schema: Mapping[str,Any]|None=None`。**`temperature` は持たない**（現行モデルは 400＝DEC-0015）。
  `load_agent_spec(path: Path) -> AgentSpec`（宣言的 YAML → dataclass。pyyaml のみ・軽い）。
- **`providers.py`**：`Provider` Protocol（`reply(*, messages, tools, spec) -> ProviderReply`）＋`ProviderReply`
  （`stop_reason: str`・`content: tuple[Mapping,...]`・`usage: Mapping[str,int]`＝Anthropic content block 形に素直）。
  `PROVIDERS: Registry[Entry]("プロバイダ", catalog="agent providers", extras_hint={"anthropic":"agent"})`。
  この骨組みでは **`dummy` kind のみ登録**：入力メッセージの正準 JSON ハッシュから決定的にテキストを返す
  （ネットワーク・課金ゼロ・seed は spec/入力から導く＝グローバル種禁止）。
- **`eval.py`**：`AGENT_METRICS: Registry[MetricEntry]("採点器", catalog="agent metrics")`。この骨組みでは
  `exact_match`（期待文字列と完全一致で 1.0/0.0）を 1 つ登録。`MetricEntry(input="label", higher_is_better=True,
  tasks=("exact",))`。description は factory docstring 1 行目（DEC-0009）。
- **`experiment.py`**：`run_agent_eval(spec, cases, *, provider, metrics, thresholds, seed) -> AgentEvalResult`。
  cases（`[{id, input, expected}]`）の各行を provider に通し exact_match でスコア化し、平均を `metrics` 名でまとめ、
  `eval.passes(scores, thresholds)` で合否。fold は無い（golden set 全体に 1 回）。返り値は指標 dict＋合否＋件数。
- **`profile.py`**：`PROFILE = Profile(name="agent", pm_checks=(lint.run_checks,))`。stdlib＋`harness.profiles` のみ import。
- **`lint.py`**：`run_checks(root)->list[pm.Problem]`。`docs/agents/**/*.yaml`（無ければ []）を **ast/テキストでなく yaml で
  読むだけ**（実行しない）、各 spec の `provider` が PROVIDERS に、`tools[]` が TOOLS に実在するか静的検査（deploy_lint 同型）。
  骨組みでは TOOLS 未実装のため tools 検査は「空なら skip・非空は将来」でよい（provider 実在検査は必須）。
- **`cli.py`**：typer `agent_app`。`agent providers`（`render_catalog(PROVIDERS)`）・`agent metrics`
  （`render_catalog(AGENT_METRICS, show_task=True)`）・`agent run --spec <path> --input <text>`（dummy で 1 応答を表示）。
  重い import は各コマンド内で遅延。`agent run` に **`--test`**（合成 spec＋合成 cases で run_agent_eval を 1 回・
  AGENTS「実験は --test 必須」の規律）。
- **`__init__.py`**：`from harness.agent.profile import PROFILE` の再export のみ。
- **配線**：`.harness/config.toml` の `profiles` に `"harness.agent"` を追加。`pyproject.toml` に extra
  `agent = ["anthropic>=0.40"]`（バージョンは着手時に確認・この骨組みでは未使用だが宣言）＋`[project.scripts]`
  に `agent = "harness.agent.cli:agent_main"`。`render_catalog` は現状 ds/cli にあるので **`harness/registry.py`（or
  新 `harness/catalog.py`）へ引き上げ**、ds/cli は import し直す（二重管理を作らない＝DEC-0009。既存 CLI 出力は不変）。
- **規約昇格（DEC-0015＝即・DEC-0012）**：`docs/decisions/DEC-0015-agent-determinism-and-provider.md`
  （temperature 廃止・effort＋cassette で決定性・provider 既定 Anthropic）。`AGENTS.md` に DS プロファイル節と並ぶ
  「agent プロファイル」1〜2 行（決定性＝effort 固定・verify は無ネットワーク）。`docs/learnings.md` に 1 件
  （温度で決定性を作れない現行モデル事情）。`docs/agent.md`（serve.md 同型・契約と CLI 導線の正本）。

## 触ってよいファイル
`src/harness/agent/**`（新規）・`src/harness/registry.py`（render_catalog 引き上げ）・`src/harness/ds/cli.py`
（render_catalog を import に変更・**振る舞い不変**）・`.harness/config.toml`（profiles 1 行）・`pyproject.toml`
（extra＋script）・`AGENTS.md`（1〜2 行）・`docs/{agent.md,learnings.md,decisions/DEC-0015-*.md}`（新規/追記）・
`tests/{test_agent_e2e.py,test_agent_catalog.py,test_agent_spec.py,test_agent_lint.py}`（新規）。
ds/serve のロジック本体は変更しない（render_catalog の移設のみ）。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_agent_e2e.py::test_agent_eval_smoke_no_network`（**e2e**）：合成 spec＋合成 cases（期待が既知）で
  `run_agent_eval`→exact_match が構成から導ける値（例：dummy が期待に一致するよう仕込んだ 3 件中 2 件一致＝0.667）に
  なり passes が閾値通り。**`monkeypatch` で `anthropic`/`httpx` の送信経路にアクセスがあれば失敗**させる（ネットワーク 0 を断つ）。
- `test_agent_catalog.py`（**unit**）：`PROVIDERS`・`AGENT_METRICS` の全項目に description（DEC-0009。test_catalog 同型）。
- `test_agent_spec.py`（**unit**）：`load_agent_spec` が YAML を読む・未知キーで失敗（extra forbid）・`temperature` キーは弾く。
- `test_agent_lint.py`（**unit**）：spec が未登録 provider を指すと error・実在 provider なら []（一時プロジェクトで）。
- `test_profiles.py`：`load_profiles` が `agent` を含み pm_checks に `lint.run_checks` が入る（既存テスト拡張）。
- exact_match の期待値は **cases の構成から導出**（実装出力のコピー＝金メッキ禁止）。`uv run verify` 全体緑。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：ネットワーク 0 の担保が本物か／render_catalog 移設で ds 出力が不変か／
dummy の決定性がグローバル種に依存していないか／profile 軽 import が壊れていないか＝subprocess で確認）
