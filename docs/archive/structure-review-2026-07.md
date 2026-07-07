<!-- 2026-07-03 の構造・設計レビュー（Fable）。EP-08 完了時点。
     resume 用：このファイル＋メモリ harness-project-state を読めば続けられる。 -->
# 構造・設計レビュー（2026-07・EP-08 完了時点）

> **解決状況（2026-07-03 追記）**：〈高①〜⑤〉〈中⑥〜⑨〉＋「入口の無い部品」＝**すべて修正済み・verify 緑・コミット済み**
> （`2784aaf` 高／`5eeb65e` 中／`ebccdc9` 入口）。高③は独立レビュー合格。未実装の約束は ISS-0002〜0005 に登録。
> **残りは〈低⑩〜⑫〉のみ＝2つ目のドメイン（アプリ開発）が出るまで意図的に保留**（Rule of Three・カタログ汎用化／
> スキル統廃合／S3・Serializer 実装・LightGBM）。「触らない方が良い所」は触っていない。

評価軸＝「エージェントファーストなプロジェクト開発の土台・ドメイン非依存・人が張り付かず機械検査で品質担保」。

## 総評
骨格は目的に合致。最大の強み＝PM 中核（work/ の木・pm.lint の完了↔検証・段階×目印の検証）と
「e2e が雛形を毎回叩く」＝本物のエージェントファースト。最大の弱点＝(1) 機械検査の無い層（スキル・DEC・
DESIGN・README）で**正本が実装とずれ始めている**（「正本は1か所」の自己違反）。(2) エージェントファーストの
仕組みが DS 実装に埋まり、汎用文書（DoD・AGENTS）に DS 固有語が漏れている。

## ドメイン非依存の結論
汎用パターン（レジストリ→一覧→スキルは導くだけ→実行される雛形→入口まで作って done）は method.md E 節に
散文で既に抽象化済み。→ **コードの汎用抽象化（`data blocks` 改名・CLI プラグイン化・レジストリ機構の中核昇格）は
2つ目のドメインまで待つ（Rule of Three）が正しい**。ただし**文書の DS 漏れの「分離」**（再配置・コード0行）は
今やる保険。

## 直すべきこと（優先度つき）
### 高（今やる・新設でなく整合）
1. **スキル腐敗の修復**：`verify` スキルの「STATUS 一致」削除（DEC-0002 で撤去済み）／`verify`・`session` の
   「完了前に uv run status」を DoD（一致は完了条件にしない）と整合。harvest に「スキルの記述が DEC と矛盾して
   いないか」の点検を1行追加。
2. **Serializer の正本ずれ解消**：実装（`ds/models.py`＝pickle 直書き＋format 文字列＋NotImplementedError＋
   warn_dependencies）を正とし、AGENTS 15行目・DEC-0006・DESIGN B-5 を「Serializer 注入案から簡素化した」に
   合わせる（実装追加でなく文書を実装へ）。
3. **E-0001 の config 化を完成**：experiment スキルは「config だけ書き換え」と言うが、モデル（LogisticRegression）と
   入力（generate_synthetic）が train.py 直書きで config から選べない＝自己矛盾。MODELS レジストリ（モデル種の一覧）
   ＋ config の `data:` 節（table_id→store.load）を足し、雛形乖離の3回目を防ぐ（DS 内の完結修正・Rule of Three 対象外）。
4. **未実装の約束を issues/ に登録**：spec_lint の `np.random.seed` 検出（method G・DESIGN C）／pm.lint の
   「昇格済み learnings が指す DEC の実在検査」（DEC-0005）／skip・xfail の ISS 参照必須（AGENTS 規約あり検査なし）／
   実験の `--test` 必須検査／holdout（最終評価）の位置づけ（EP-04 の fixed_split が実験ループから切断）／slow の回し先。
5. **pyproject の slow マーカー説明の修正**（checks.toml は全段階 not slow と矛盾・1行）＋ **README 修正**
   （`../draft/output` のリポ外パス正本指定を削除・E-0001 の場所を EP-04→EP-06 に訂正・charter の「テンプレート化は
   やらない」を EP-08 が実質やった旨）。

### 中（テンプレートを次案件に複製する前まで）
6. DoD・AGENTS の DS 固有文言を「DS プロファイル」節へ分離（コード抽象化はしない・文書の再配置のみ）。
7. `checks.py` の `from harness.ds import schema` 直 import 解消（data_lint を中核へ or 検査登録リスト）。
8. DESIGN.md の畳み込み＋汎用部の救出（段階×目印の機構・store/models の4作法を docs/ へ・checks.toml のコメント
   参照先を直す）。EP-06 done を機に R 節中心へ旧節を削る。
9. テンプレート複製手順の1ページ（消す＝work/EP-01..08・REQ・ISS・charter／残す＝DEC・method・DoD・スキル・src・
   tests。test_e2e_experiment.py が work/EP-06 のパス直書き＝複製手順を決めないと verify が壊れる）。

### 低（2つ目のドメインが出たら・Rule of Three）
10. カタログコマンドの汎用化（`data blocks` 改名・CLI のプロファイル登録機構）・レジストリ機構の中核昇格。
11. plan/tasks・session/verify のスキル統廃合（発火が割れた記録が learnings に2回出てから）。
12. S3/DWH/GitHub アダプタ・Serializer 実装・LightGBM（宣言済みの保留どおりで正しい）。

## 触らない方が良い所
pm.py の木モデルと lint 群／段階×目印＋未マーク失敗ガード＋門番空回り検査（一番良くできている）／run_cv の
clone-per-fold と ds/ の平ら構成／「E-0001＝実行される雛形」方式（.harness/templates 別置きは腐るので逆行）／
STATUS 非コミット（DEC-0002）／issues を木の外（DEC-0003）／汎用機構の先行作成（method の Rule of Three どおり作らない）。

## 入口の無い部品（DEC-0009 の自己違反・要点検）
`data.fixed_split`／`cv.holdout_indices`／`eval.select_threshold_at_recall`/`at_precision`／`models.promote_model`
（CLI もスキルも導線ゼロ）／`models.load_model`（推論の物語が無く孤立）。
