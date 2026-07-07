---
id: T-0092
kind: task
status: done
title: 実プロバイダ（AnthropicProvider・遅延/verify 経路外）＋CassetteProvider（記録再生・fail-closed）
created: 2026-07-06
depends_on: [T-0089, T-0091]
verified_by: [tests/test_agent_cassette.py::test_cassette_replay_matches_adapter_no_network]
---
# T-0092 実プロバイダ＋cassette（記録再生で SDK 応答形状のドリフトを無ネットワークで検知）

## 狙い（骨組みの dummy を実プロバイダに差し替える口＝ただし verify は無ネットワークのまま）
T-0089 で `PROVIDERS` に dummy だけ登録した。実運用は Anthropic を呼ぶ。だが**verify はネットワーク 0 が契約**
（DEC-0015）。そこで実プロバイダ（`anthropic` SDK・遅延 import・verify 経路外）と、**記録再生（cassette）**を分ける：
実 SDK 応答を 1 度記録した固定フィクスチャを再生し、**SDK 応答形状→ProviderReply の変換（adapter）**を無ネットワークでテストする。
adapter は AnthropicProvider（実呼び出し）と CassetteProvider（再生）で**共有**する＝実 SDK の応答形状が変わったら
cassette の再記録で検知できる（記録が無ければ **fail closed**＝黙って通さない）。

## 受け入れ基準（`providers.py` 拡張・`agent/cassette.py` 新規・軽 import 規約＝DEC-0013・無ネットワーク維持）
- **応答 adapter（純関数・共有）**：`_reply_from_anthropic(data: Mapping[str,Any]) -> ProviderReply`。
  入力は Anthropic Messages API 応答の dict（`resp.model_dump()` 相当＝`{"content":[{"type":"text","text":…}|{"type":"tool_use","id":…,"name":…,"input":…}], "stop_reason":…, "usage":{"input_tokens":…,"output_tokens":…}}`）。
  content ブロックを ProviderReply.content にそのまま写し（text/tool_use の形は T-0091 の run_agent が理解する形と一致）、stop_reason・usage を移す。
  **anthropic を import しない**（dict だけ受ける＝無ネットワークでテストできる・SDK 不在でも動く）。tool_use の `input` が無い等の欠損は明示エラー（黙って握りつぶさない）。
- **`AnthropicProvider`（実プロバイダ・遅延 import・verify 経路外）**：`reply()` の**中で** `import anthropic`（top では import しない＝
  extra `agent` 無しでも `import harness.agent` が壊れない・軽 import を守る）。`anthropic.Anthropic()`（API キーは環境変数＝
  **コードは読まない・プロンプトに書かない**）で `messages.create(model=spec.model, system=spec.system_prompt, messages=…, tools=…,
  max_tokens=…, extra_headers/【effort】=spec.effort)` を呼び、`resp.model_dump()` を `_reply_from_anthropic` に通す。
  **temperature は送らない**（DEC-0015＝現行モデルは 400）。effort の渡し方は着手時に SDK/API を確認（thinking/effort パラメータの現行仕様）。
  PROVIDERS に `anthropic` kind で登録（factory は seed を受けるが実呼び出しでは未使用＝署名互換）。extras_hint は既存（`{"anthropic":"agent"}`）。
- **`CassetteProvider`（記録再生・fail closed・integration）**：`agent/cassette.py`。
  - cassette＝JSONL/JSON ファイル：キー＝`(model, system_prompt, messages, tools)` の**正準 JSON の sha256**（`harness.fingerprint.input_fingerprint` を再利用）→ 値＝記録した応答 dict（`model_dump` 相当）。
  - `record` モードは**この骨組みでは作らない**（実記録はネットワーク＝verify 外。フィクスチャは API 契約から手で書く＝金メッキでなく仕様の写し）。
  - `replay` のみ：`reply()` はキーを計算し cassette から応答 dict を引き、`_reply_from_anthropic` に通す。**記録が無ければ ValueError（fail closed）**＝黙って dummy 応答にフォールバックしない。
  - `CassetteProvider(seed, *, path)` を工場で作る（PROVIDERS には登録しない or `cassette` kind で登録＝テスト/CI 用。決めて docstring に明記）。
- **CLI/カタログ**：`agent providers` に anthropic（＋cassette）が説明つきで載る（DEC-0009・description は factory docstring 1 行目）。
  実プロバイダの実行は extra 必須の旨を出す（既存の一文を維持）。
- **開発環境**：`uv sync --all-extras`（AGENTS の DS プロファイル規約）で anthropic を dev/verify env に入れ、mypy が AnthropicProvider を型検査できるようにする（ただし**実行時 import は遅延**のまま＝verify のテストは anthropic を読み込まない）。extra 無しの利用者環境でも `import harness.agent` は軽いままであることを subprocess テストで固定（既存の軽 import テストに anthropic を含む）。

## この骨組みでやらないこと（soon/later・理由つき）
- **実記録（record モード）・実 API 結合テスト**は verify に載せない（ネットワーク＝DEC-0015 違反）。cassette は API 契約から書いた固定フィクスチャで形状を守る。実記録スクリプトが要るなら別スライス（手動・CI 秘匿環境）。
- **複数プロバイダ同時実装はしない**（PROVIDERS が差し替え軸・Anthropic 1 社で足りる・必要時に即＝item.md/DEC-0012）。
- **ストリーミング（SSE）・リトライ/レートリミッタ**は LLM ゲートウェイの関心＝やらない（item.md の later）。

## 触ってよいファイル
`src/harness/agent/providers.py`（adapter＋AnthropicProvider＋登録）・`src/harness/agent/cassette.py`（新規）・
`src/harness/agent/cli.py`（providers 一覧は自動・必要なら文言）・`pyproject.toml`（既存 extra の版確認のみ）・
`docs/agent.md`（実プロバイダと cassette の節）・`.claude/skills/**`（1 行）・
`tests/{test_agent_cassette.py,test_agent_providers 相当}`（新規）＋既存 `tests/test_agent_lint.py` の軽 import テストに anthropic 追加。`ds/**`・`serve/**` は変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須・無ネットワーク）
- `test_agent_cassette.py::test_cassette_replay_matches_adapter_no_network`（**integration**）：API 契約から書いた
  応答フィクスチャ（text ブロック＋tool_use ブロックの 2 例）を cassette に置き、CassetteProvider.replay が
  `_reply_from_anthropic` と同じ ProviderReply を返す。**socket を塞ぐ**（ネットワーク 0）。記録の無いキーは ValueError（fail closed）。
- `_reply_from_anthropic` の変換（**unit**）：text のみ／tool_use 込みの dict から stop_reason・usage・content が正しく写る（構成した dict から導く）。欠損（tool_use に input 無し等）は ValueError。
- CassetteProvider を `run_agent`（T-0091）に挿すと、tool_use→tool_result→end_turn の往復が cassette 2 応答で回る（**integration**・無ネットワーク）＝実プロバイダに差し替えても run_agent が不変であることを固定。
- AnthropicProvider は**温度を送らない**：`messages.create` をモンキーパッチ（or 記録した呼び出し引数を捕捉）し、temperature キーが渡らない・effort が渡ることを確認（**unit**・anthropic の実クライアントは作らない＝create だけ差し替え）。ネットワークは張らない。
- 軽 import 維持（**integration**・subprocess）：`import harness.agent` で anthropic/httpx/fastapi/uvicorn/polars/sklearn 未ロード（AnthropicProvider の import が遅延であることの証明）。
- `PROVIDERS` の全項目（dummy/anthropic/cassette）に description（**unit**・DEC-0009）。
- 期待値は応答フィクスチャ・呼び出し引数の構成から導く（金メッキ禁止）。`uv run verify` 全体緑。`verified_by` の名がテストに実在。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
実装は fable。レビューは別文脈・別モデル（Opus）が差分のみを実測・変異で確認（APPROVE）。3 変異はいずれも
バイト同一に復元、変異中は狙ったテストだけが RED になることを確認済み。
- **cassette の fail closed＝変異で確認**：`CassetteProvider.reply` の `if record is None:` を `and False` で
  無効化 → `test_cassette_replay_matches_adapter_no_network`・`test_cassette_provider_is_replay_only` が RED
  （記録欠けで黙って dummy へ落ちる抜け道が無いことを捕捉）。
- **temperature を送らない＝変異で確認**：`output_config={"effort": …}` を `temperature=0` に差し替え →
  `test_anthropic_provider_sends_effort_not_temperature` が RED（現行モデルが 400 を返す送信を捕捉・DEC-0015）。
- **adapter の fail loud＝変異で確認**：未知 block type の `raise` を `continue`（黙って捨てる）に差し替え →
  `test_adapter_rejects_unknown_block_type` が RED（SDK 応答形状のドリフトを見逃す抜け道が無いことを捕捉）。
- **run_agent 不変**：`test_run_agent_through_cassette_tool_loop` が cassette 2 応答で tool_use→tool_result→
  end_turn を 2 ターン・無ネットワークで回す（実プロバイダ差し替えで往復ループが不変。期待 usage 30/12 は
  フィクスチャの構成から導出＝金メッキでない）。
- **軽 import 維持**：`test_import_harness_agent_stays_light` に providers/cassette/AnthropicProvider の import を
  足しても anthropic/fastapi/uvicorn/polars/sklearn は未ロード（reply() 内の遅延 import の証明・DEC-0013）。
- **無ネットワークの担保が本物**：両 integration テストは `block_network`（`socket.socket` を raise 差し替え）で
  実ネットワークへ出た瞬間に失敗する。AnthropicProvider のテストは `anthropic.Anthropic` を偽物に差し替え＝
  実クライアントを作らない（create の引数だけ捕捉）。
- **プロファイル境界／発見性**：cassette は `cassette` kind で PROVIDERS に登録され `agent providers` カタログに
  説明つきで載る（DEC-0009）が、工場 `cassette_replay` は providers.py 側の遅延 import で循環を避ける。全 provider
  （dummy/anthropic/cassette）に description（`test_all_providers_have_descriptions`）。
- **verify 全体緑**（`成功（すべて通過）`）。指摘なし。
