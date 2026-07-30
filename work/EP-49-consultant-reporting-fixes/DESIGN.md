# EP-49 設計：EP-48 レビュー是正

独立レビューの CONFIRMED 3 件（D1/D2/D3）と、保留の中程度（A/B/C/D/E/F）と、非ブロックの弱い指摘のうち
安価で価値のある 1 件（W1）を是正する。各修正は既存の大原則を崩さない。

## D1 報告のマイルストーン粉飾（report.py）
done だが `closed`（実績終了）が無いマイルストーンで、`_fmt(done_day or row.due)` が**予定日を「実績」と
名乗って**出す。pm も wbs_lint も done に `closed` を要求しないため到達可能。
- 直し方：`actual_finish` が無ければ「実績日の記録なし」と明記し、予定日を実績として刻まない。遅延判定も
  `actual_finish` があるときだけ行う（記録が無いのに「遅れて達成」と決めない）。
- 原則との整合：fail-closed（不明を都合よく埋めない）・粉飾しない（DESIGN が最優先で禁じた形）。

## D2 `--against` 経路が関門の外で組み立てる（cli.py）
`report --against` の `changes_since` と `export --against` の `baseline_map` が `_prepare` より先に木を
組み立て、組み立て失敗（pydantic ValidationError＝ValueError）が素の traceback になる。
- 直し方：`report` は `_prepare` を先に通し、`changes_since`／`baseline_map` の呼び出しは `BaselineError`
  だけでなく `ValueError`／`OSError` も `_fail` に畳む（拒否連鎖の単一実装に戻す）。

## D3 依存ホバーの検証欠落（tests）
T-0284 の受け入れ基準 (c)「かざすと dep-hi が付く（ヘッドレス実測）」に対応する自動テストが無く、逆写像・
`mark` の変異が緑のまま通る。
- 直し方：実ブラウザ（headless Chrome）で `mouseenter` を発火させ `--dump-dom` の DOM に `dep-hi` が
  先行・後続の両方向へ付くことを確かめるテストを足す。土台（ロケータ＋dump-dom 実行）は `tests/_headless.py`
  に置いて再利用可能にする。Chrome が無い環境は ISS-0018 を参照して skip（データ側検査・JS 構文検査は常に回る）。

## A 取り込み後にセッションの土台が古いまま（session.py / server.py）
`apply` は新しい土台の `Session` を作って保存するが、サーバはそれを受け取らず古い `edit` を持ち続ける。
2 度目の `apply` が `drifted()`（正本が自分の apply で動いた）で誤って 409 になる（「続けて編集できる」設計に反する）。
- 直し方：`apply` が新しい `Session` も返し、サーバは `nonlocal` で `edit` を差し替える。`discard` も返り値を使う。

## B 由来の指紋が表示値の一部しか覆わない（stamp.py）
docstring は「表に出ている値そのもの」と言うが、`tree_fingerprint` は code/ref/name/status/start/due だけで、
team・担当・工数・実績日・milestone・進捗・出来事を覆わない（担当だけ変えた 2 版が同じ指紋になる）。
- 直し方：表示する値すべて（＋出来事の開催日）を指紋に含める。`late` は基準日由来なので入れない（生成日は別欄）。

## C/D 参照検査の穴（wbs_lint.py）
- C：手動行の `depends_on` が実在しない ID を指しても検査が素通りする（pm は手動行を知らない）。
  → 手動行の各 depends_on が「作業単位 ID ∪ 手動行 ID」に在ることを wbs_lint で検査する。
- D：依存順序の検査が `start is None` でマイルストーンを飛ばす。マイルストーンの実効開始＝`due` として検査する。

## E 折りたたみが末端に三角を書く（render.py）
`setAll` が `.tw`（末端の空 `<span class="tw">` を含む）すべてに `▸`/`▾` を書き込み、末端行に無いはずの三角が
出る。個別クリックの `closest('.tw')` も同じ。
- 直し方：トグルの対象を `button.tw`（親行の実ボタン）に限る。

## F 定例会議の置き場の矛盾（docs/deliver.md・overlay.py）
`events`（有限個の開催日・完了なし）が定例会議の正しい置き場と明記しつつ、別の段落と docstring が定例会議を
「手動行（rows）」や「start・due を持つ期間の帯」として置けと書いており矛盾する。
- 直し方：定例会議は `events` に一本化する記述へ直し、rows の例は承認待ち・先方の作業に置き換える。

## W1 報告の見出しに解決コミットを併記（report.py・cli.py）
`report` の見出しが `合意した時点: <ref>` だけで、ref がブランチ名だと後から動く。`stamp.label_for` で解決した
コミットを併記する（`export --at` と同じ扱い）。

## やり方
全体→詳細。各修正に、入力の作り方から期待値を導くテストを付け、`uv run verify` を全成功に保つ。
是正後に別セッションの独立レビューを通す（重大指摘が消えるまで done にしない）。
