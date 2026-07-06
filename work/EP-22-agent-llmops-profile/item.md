---
id: EP-22
kind: epic
status: in-progress
title: LLMOps/AgentOps プロファイル harness.agent（LLMエージェントの一般ライフサイクル）
plan: detailed
requirements: [REQ-002]
depends_on: [EP-14, EP-17]
created: 2026-07-06
---
# EP-22 LLMOps/AgentOps プロファイル（harness.agent）

## 目的（この依頼の本体＝エージェント"を"開発・運用する基盤）
MLOps ハーネスを **LLMOps/AgentOps** へ拡張する。対象は「エージェント"を使った"開発」ではなく、
**LLM エージェント"そのもの"を開発・運用する基盤**（MLOps/DevOps の拡張）。DEC-0014 の「ハーネスは
ライフサイクル全体」を LLM 領域へ延ばす。中核アーティファクト＝**1 エージェント＝宣言（prompt＋model＋
tools＋方針）**。ライフサイクルは ML と同型：宣言 → 評価データ（golden set）→ 採点（LLM-judge/rubric/exact）
→ 変種比較（experiment）→ 評価スコアで昇格（promote）→ 配信（serve）→ 監視（品質/コスト/ドリフト）。
既存プロファイル境界（DEC-0004）に **新プロファイル `harness.agent`** として閉じる（中核・ds・serve は無傷）。

## 設計の核（3 本の独立調査を統合・翻案前提）
既存の「評価→合否→昇格」骨格はほぼ同型で流用でき、**真に新規なのは 2 つだけ**：(1) 宣言的 `AgentSpec`、
(2) プロバイダ抽象（ネットワーク無しでも回る dummy/cassette）。残りは既存部品の再利用か軽いパラメータ化。

| LLMOps が要るもの | 既存で足りる | 新規/変更 |
|---|---|---|
| 採点器カタログ | `Registry`/`MetricEntry`/`render_catalog`（description 必須＝DEC-0009） | `AGENT_METRICS` インスタンス＋LLM 系 factory |
| 合否ゲート | `eval.passes()`（向き付き・fail closed） | そのまま |
| 変種比較 | `experiment.leaderboard()`（NaN 最下位・決定的ソート） | fold 無し版 `run_agent_eval` |
| 保存＋champion 昇格 | `models.promote_model`（絶対関門＋相対関門）・`harness.storage`（manifest/指紋/来歴） | `promote_model` に `metrics=` 引数追加（後方互換）→ agent から `AGENT_METRICS` で呼ぶ |
| golden set | `store`（layer×scope×role・検証済みのみ保存・指紋） | `role: eval` を足すだけ（第4層は作らない） |
| 実行ログ | `serve/runtime` の JSONL 契約（`PREDICTION_LOG_FIELDS`・`input_fingerprint`・`append_jsonl`） | `AGENT_LOG_FIELDS` 別契約＋`input_fingerprint` を core へ引き上げ |
| ドリフト監視 | `ds/monitor` の psi/band（門番にしない）・`eda.psi` | agent 版 `monitor`（品質/コスト/拒否率へ流用） |

**決定性の要（DEC 化する非自明点）**：Opus 4.7/4.8・Sonnet 5・Fable 5 では `temperature`/`top_p`/`top_k` が
**パラメータごと廃止（送ると 400）**。旧来の `temperature=0` で決定性を作る手は使えない。ハーネス側の決定性軸は
**(a) `effort`（low〜max）を AgentSpec の一部として固定**、**(b) verify では実 API を叩かず記録再生（cassette）**の 2 つ。
モデル出力自体は非決定でよい（分散は本番監視で見る）。プロバイダ既定＝Anthropic Claude（既定 `claude-opus-4-8`、
高頻度・低コストは `claude-sonnet-5`）。→ DEC-0015 で正本化。

**非対称（過剰設計の回避）**：agent の実体は宣言的 YAML そのもの（学習済みバイナリではない）。ゆえに
ds の `FORMATS`（pickle/skops/onnx の差し替え口・DEC-0006）に当たる機構は **要らない**（manifest 1 形式で足りる）。

## パッケージ構成（`src/harness/agent/`・軽 import 規約＝DEC-0013）
```
__init__.py   PROFILE の再export のみ（重い依存を top import しない）
profile.py    PROFILE = Profile(name="agent", pm_checks=(lint.run_checks,))  stdlib＋harness.profiles のみ
spec.py       AgentSpec（frozen・extra forbid）＋load_agent_spec（宣言的 YAML → dataclass。DEC-0004 同型）
providers.py  PROVIDERS: Registry[Entry]＋Provider Protocol＋dummy（決定的・無ネットワーク）。anthropic/cassette は soon
eval.py       AGENT_METRICS: Registry[MetricEntry]（exact_match・dummy_judge → soon で rubric/json_schema）
experiment.py run_agent_eval（fold 無し）＋leaderboard 流用（当面は複製・3 箇所目で core 昇格を DEC 化）
store.py      save_agent/load_agent/champion/promote_agent（harness.storage 再利用・promote_model を metrics= で呼ぶ）
runtime.py    step/run_agent（純関数ループ）＋AGENT_LOG_FIELDS 契約＋build_log_rows（重い依存なし）
tools.py      TOOLS: Registry[Entry]＋ダミーツール（echo 等・無ネットワークでループ検証）
lint.py       agent_lint：AgentSpec の tool/provider kind が Registry 実在かを静的検査（deploy_lint 同型）
cli.py        typer：agent providers|tools|metrics|run|experiments（重い import は各コマンド内で遅延）
app.py        soon：FastAPI /invoke（fastapi は module top import・profile.py からは辿らせない）
monitor.py    soon：agent monitor（eda.psi 流用・門番にしない）
guardrails.py soon：JSON schema 検証＋InputGuard Protocol＋正規表現 PII スタブ（検出モデルは委譲）
```

## 進め方（歩く骨組み→差し替え・verify 緑を保つ・独立レビュー）
- **T-0089 歩く骨組み**（detailed）：宣言 → dummy provider → 採点(exact_match) → 合否(passes) → 検証(--test/verify)
  が一巡する最小。profile 登録・カタログ CLI・e2e スモーク・catalog テスト・DEC-0015 まで。**ネットワーク 0** をテストで断つ。
- **T-0090 昇格ライフサイクル**（detailed）：`promote_model` に `metrics=` 追加 → `store.py`（save/champion/promote_agent）→
  golden set を store テーブル(`role: eval`)化 → `agent experiments`（leaderboard）。「評価スコアで昇格」を一巡。
- **T-0091 ツール往復ループ**（detailed）：`TOOLS`＋`runtime.step/run_agent`（純関数）＋`AGENT_LOG_FIELDS`。
  `input_fingerprint` を core（`harness/fingerprint.py`）へ引き上げ serve/agent 共用。
- **T-0092 実プロバイダ＋cassette**（outline・soon）：`AnthropicProvider`（遅延 import・verify 経路外）＋`CassetteProvider`
  （記録が無ければ fail closed・integration マーカー）。実 SDK 応答形状のドリフトを無ネットワークで検知。
- **T-0093 監視＋ガードレール**（outline・soon）：`agent monitor`（eda.psi 流用・品質/コスト/拒否率・門番にしない・
  `--file-issue` 冪等起票）＋`guardrails`（JSON schema 検証＋PII 正規表現スタブ＋Protocol）。
- **T-0094 配信**（outline・later 寄り）：`/invoke`（会話履歴・ツール往復。`/predict` と別 app）＋`agent serve`。

## やらないこと（later・順序の問題であって対象外ではない＝DEC-0014）
複数プロバイダ同時実装（差し替え軸=PROVIDERS は用意・実装は Anthropic 1 社で足りる・必要時に即＝DEC-0012）・
OpenTelemetry 実エクスポート（ログ契約のキー名を gen_ai.* 語彙へ寄せるまで・collector 常駐は利用者環境=DEC-0013）・
ストリーミング(SSE)・マルチエージェント委譲・pairwise/ELO・judge アンサンブル・レートリミッタ/セマンティックキャッシュ
（LLM ゲートウェイの関心）・prompt レッドチーム（別関心・別 DEC）・agent 版 Docker/K8s テンプレ（配信が固まってから複製）。
いずれも DEC-0014 の対象内で順序後回し。過剰設計の釘：AgentSpec 用 FORMATS・自前プロンプトテンプレエンジン・
guards の早すぎる Registry 化（2 実装目で昇格）・eval 専用第4データ層は作らない。
