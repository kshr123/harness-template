# EP-48 設計（SPEC）：コンサル提出層の報告・トレース・ベースライン・依存・xlsx体裁

独立設計レビュー（fable・maker≠checker）の指摘を反映済み（改訂 1）。方向は妥当・要修正 4 点＋補強を取り込んだ。

## 貫く原則（全機能で守る）
- **二重台帳を作らない**：日程・状態・階層・要件・依存はすべて既存の正本（`work/` frontmatter・`docs/wbs.yaml`・
  `docs/requirements`・`docs/demands`）から**導出**する。新しい保存欄・第 2 のパーサ・第 2 の座標/拒否/色の実装を
  作らない（＝漂流源を作らない）。
- **fail-closed**：出力系は既存の `export` と同じ拒否（lint エラー→日程 0 件→WBS 入力が未コミット）を**同じ 1 本の
  共有関数**で通す。`--against`/`--at` の参照は実在必須。要求/要件層が無い案件は空表示＝正常だが、それが正しく
  「空＝正常」になるよう、**書いたのに黙って出ない経路は lint 側で塞ぐ**（下記 T-0283 の pm 修正）。
- **理想を基準にする（容量・抽象度で決めない）**：行数を削るために意味のまとまりを潰さない／抽象化のための抽象化も
  しない。原則（正本 1 つ・導出のみ・fail-closed・座標 1 実装・エスケープ必須）に一番きれいに乗る構造を選ぶ。
- **造語を作らない**：画面語は既存語を再利用（変化・マイルストーン・遅れ・予定・要件・要求・**未カバーの要件**・
  合意した時点）。新しい名詞を作らない。英語オプション名は docs で日本語の説明に紐づける。
- **座標は 1 実装**：`render._pct`/`_day_pct` のみ。**描画窓は現行 span とベースライン地図の min/max の合併**から作る
  （窓外の日付で `_pct` が 0–100% を外れないように。座標式そのものは 1 本のまま）。
- **出力エンコード**：新しい出力面すべてで利用者由来文字列を `_esc`（HTML）／`xlsx._put`（数式無害化）に通す。回帰テスト必須。

## 共有部品（実装の土台・第 2 実装を作らないための切り出し）
- `cli._refuse_or_build(root, today, commit) -> (built, provenance, draft)`：**拒否の連鎖（lint→0件→未コミット）を
  1 か所に切り出す**。`export` と `report` が同じ 1 本を通る（拒否の順序・文言の第 2 実装を作らない）。
- `render.SHARED_STYLE`（色トークン＋基本体裁の最小定数）：report もこれを参照する。`_STYLE` の部分コピーをしない
  （色トークンの第 2 台帳＝ダークテーマ追随漏れを防ぐ）。
- `pm.requirement_trace(root) -> {known: set, referenced_by: {REQ: [work_id...]}, uncovered: set}`：REQ の glob・ID 規則・
  work→REQ の突き合わせを**1 か所**に。`pm.check`（lint）と report の被覆ビューが同じ導出を見る。

---

## T-0281 `wbs report` — 定例/最終報告の 1 枚（最優先）
**コマンド**：`uv run wbs report [--against <ref>] [--out <path>] [--today YYYY-MM-DD] [--horizon-days 14] [--draft] [--root <root>]`
出力は自己完結 HTML（既定 `artifacts/wbs/REPORT.html`）。ガントでなく**報告の 1 枚**（印刷→PDF 前提）。

**構成（すべて既存の導出から。0 件の節はすべて「無し」と明記＝黙って消さない）**：
1. 見出し：案件名・本日・由来の刻印（`stamp.stamp`）。`--against` 時は「合意した時点: <ref>（解決コミット）」も。
2. **前回からの変化**（`--against` 時のみ）：`baseline.changes_since(root, ref, today)` の `Change.line()` を種類で束ねる。
   未指定なら節ごと省略（空節を出さない）。
3. **マイルストーンの状況**：`walk()` の `milestone and due` を **達成／遅れ／予定** に分ける。
   **達成は `actual_finish`（closed）の実日付で示し、`actual_finish > due` なら予定と実績の両日付を出す**
   （期日超過後の達成を「達成◆」で粉飾しない）。0 件なら「該当なし」。
4. **遅れている作業**：`row.late` の末端行（予定終了・担当・遅延日数＝today−due）。0 件なら「遅れなし」。
5. **今後 N 日の予定**：`today ≤ start ≤ today+horizon` か期間が窓に掛かる末端行。既定 14 日。0 件なら「該当なし」。
6. 付録：要件トレース（T-0283。REQ が無ければ節ごと出さない）。

**モジュール** `report.py`（`_DOCUMENT`・`_esc`・`render.SHARED_STYLE` を使う）。CLI は `cli.py` に追加、拒否は
`_refuse_or_build` を通す。coverage_lint に載せ、docs/skill から導線。

**受け入れ基準**：
- (a) tmp git リポジトリで「T-X の due を 8/1→8/8 に動かすコミット」を作り、**その前後の日付とコミット件名**が
  「前回からの変化」に出る（同じ関数のエコーでなくテストデータ由来の具体値で検査）。
- (b) done／期日超過で未完／未来 の 3 マイルストーンが各 1 区分に出て、**closed>due の達成が遅れて達成と読める形**で出る。
- (c) lint 失敗・未コミット・日程 0 件で出力しない（`_refuse_or_build` 経由）。
- (d) 遅れ 0 件で「遅れなし」・マイルストーン/今後 0 件で「該当なし」と出る。
- (e) 利用者文字列がエスケープされる／外部リソース参照ゼロ。

---

## T-0282 ベースライン重ね描き（`export --against <ref>`）
**何を**：合意時点の棒を淡色で背後に重ね、現状の棒と縦にずらして並べる。`export` に `--against <ref>` を追加。

**設計**：`tree_at(ref)`+`build` で過去断面 Wbs → `_key`（ref か 節名）で `{key: (start, due)}` の地図。
`render.render_html(..., baseline=<map>)` を追加、`_bar_html` が淡い第 2 の棒（`.gbar-base`）を現状の棒の下に描く。
**描画窓は現行 span と地図の日付の min/max の合併**から作る（`_pct` は 1 実装のまま、0–100% に収める）。
色は既存の淡青（`--done` 相当）を `.gbar-base` に（新色なし）。

**組み合わせの規定（fail-closed）**：`--against` は baseline が実在検査。**`--against` × ベースライン非対応形式
（xlsx 等）は明示的に拒否（exit 1）**＝黙って層を落とさない。`--at` と `--against` の同時指定も拒否。
**ベースラインのマイルストーン（start 無し・due のみ）はガント重ね描きから除外**し、日程移動は report の変化節で示す
（黙って落とさない、と docs/help に明記）。

**受け入れ基準**：(a) 合意時点と現状で日程が違う行に淡い第 2 棒が出て `_at()` 由来の期待値と一致、
(b) **現行窓の外の日付を持つベースライン行でも left/width が 0–100% に収まる**、(c) 未指定時は第 2 棒が一切出ない、
(d) `--against`×xlsx と `--at`×`--against` が exit 1、(e) 既存 geometry テストが緑（座標第 2 実装なし）。

---

## T-0283 要件トレース被覆ビュー（DEM→REQ→work）
**先に塞ぐ fail-open（pm）**：`pm.py` の work→REQ 参照検査は現状 `if req_dir.is_dir():` の中にあり、
`docs/requirements/` が無い案件では `requirements: [REQ-001]` と書いても error にならない（satisfies 側は
既に fail-closed）。**satisfies と対称に、req_dir が無くても非空の `requirements` は参照エラーにする**。これで
「REQ 層が無い案件は被覆節を出さない」という F3 の判断が正しく「空＝正常」になる（書いたのに黙って出ないが消える）。

**データ源**：work→REQ は `Item.requirements`（**WbsRow に `requirements` を導出で足す**・保存欄なし・`default_factory=list`）。
REQ→DEM・REQ 名は `docs/requirements/REQ-*.md`／`docs/demands/DEM-*.md` の frontmatter。**読み取りは
`pm.requirement_trace`（共有 loader）を使い、glob・ID 規則の第 2 実装を作らない**。

**ビュー（report 付録のみ。export フッタには出さない＝同じ表を 2 面に出さない）**：REQ ごとに
「REQ-id・名前・満たす作業（ID＋状態）・**未カバーの要件**（作業ゼロ）」。任意で DEM→REQ の段。
**REQ ファイルが無い案件は節ごと出さない**（空表を出さない）。可視化でありゲートではない（参照切れは pm が error）。
画面語は pm 既存の「未カバーの要件」を再利用（造語しない）。

**受け入れ基準**：(a) REQ を参照する作業がある案件で REQ→作業→状態が出る、(b) **未カバー集合が同じ入力の
`pm.check` の info（未カバーの要件）と一致**、(c) REQ ファイルが無い案件で節が出ない、(d) req_dir 不在でも非空
`requirements` が lint error（pm 修正のミューテーション）、(e) 利用者文字列がエスケープされる。

---

## T-0284 依存の可視化（ホバーで先行/後続）
**何を**：行にかざすと先行（depends_on）と後続（逆写像）を淡くハイライト（矢印なし・クリティカルパスは範囲外）。

**設計**：`_row_html` に `data-deps`（**JSON 配列**。ID に空白が入っても壊れないよう空白区切りにしない）を足し、
後続は先行の逆写像を JS で 1 回作る。ハイライトは既存 `--sel`/`--hover` の範囲（新色なし）。render.py 内で完結。

**受け入れ基準**：(a) 各行に `data-deps`（JSON）が出て中身が depends_on と一致、(b) JS が構文として通る、
(c) **ヘッドレスで hover を発火させ、先行/後続の `tr` にハイライト class が付く**（DOM で確認＝このプロジェクトの
「UI は描画で確認」既定に一致）。

---

## T-0285 xlsx の体裁パリティ（低優先）
**何を**：週の列に非稼働日を含む週の淡い網掛け・本日を含む週の縦線・凡例行を足し、HTML と「同じ意味・同じ色」に
近づける。週粒度は据え置き。色は `_FILL`＋既存の意味色のみ（新色なし）。数式無害化（`_put`）は維持。

**受け入れ基準**：(a) 本日を含む週の見出しに印、(b) 凡例が出る、(c) 既存の「木と一致」テストが緑（値の対応を
壊さない）、(d) `=+-@` 始まりの利用者文字列が data_type 's'（数式無害化の維持）。

---

## 実装順とレビュー
着手順：T-0281（＋共有部品 `_refuse_or_build`・`SHARED_STYLE`）→ T-0282 → T-0283（＋pm の fail-open 修正・
`requirement_trace` 抽出）→ T-0284 → T-0285。各タスクは実装→`uv run verify` 緑→**別モデル(fable)で独立レビュー＋
効かせる guard のミューテーション（RED 実測）**→コミット。**ミューテーションの後始末に `git checkout` を使わない**
（未コミットの本実装まで戻る＝EP-47 の教訓）。コミット後に検証するか、mutation を手で元に戻す。
