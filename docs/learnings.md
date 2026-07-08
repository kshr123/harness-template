# learnings（気づき・使いにくかった点の記録）

この文書は、作業で得た気づき・使いにくかった点を、ルールへ格上げ（ルール化）する前の
材料として記録する場所。同じ失敗を繰り返さないために、作業者（人・エージェント）が随時書く。
1 件＝1 項目で、冒頭に要点、続けて背景と対応。リポジトリや履歴が既に記録することは書かない。古くなったら消す。

各項目は「状態」を持つ：
- **記録のみ** … まだルール化していない観察。
- **ルール化済み** … 機械検査・抽象・スキル・規約のどれかへ落とした（現在のルールは AGENTS/method/検査が正本。経緯は git）。次の見直しで消す（ただし他の learnings の**根拠として引用されている**ものは、引用先が迷子にならないよう先例として保持する＝L-004 の扱い）。

ルール化の流れは `docs/method.md` C 節、実行手順は harvest スキル。L-001〜003・005〜006 は実装知識でルール化不要（記録のみ）。L-004 はルール化済み（生成物 STATUS の扱い）で、後戻り防止（歯止め）の先例。

---

## L-001 Windows のコンソール（cp932）は ✓ などの記号を出せず落ちる
- **要点**：出力に `✓✗` や日本語があると、Windows の既定の文字コード（cp932）で `UnicodeEncodeError` になり落ちる。
- **対応**：CLI の起点（`harness/cli.py`）で `sys.stdout/stderr.reconfigure(encoding="utf-8")` を最初に実行し、出力を UTF-8 に固定。「make に依存しない＝複数の OS で動く」前提の一部。
- **設計への反映**：不要（実装で解決）。「CLI は UTF-8 に固定する」は AGENTS.md の範囲で足りる。

## L-002 mypy strict ＋ 型情報の無い外部ライブラリ（python-frontmatter）は取り込みで失敗する
- **要点**：strict だと、型情報の無いライブラリの取り込みで失敗する。
- **対応**：`pyproject.toml` に `[[tool.mypy.overrides]] module=["frontmatter"] ignore_missing_imports=true` を追加。
- **設計への反映**：不要。新しい外部ライブラリを足したとき同じ設定が要ることがある、と覚えておく。

## L-003 日本語のコメント・メッセージは ruff の行の長さにすぐ当たる
- **要点**：日本語は文字が詰まるため、説明的な文が長くなりやすい。造語を使わず平易に書くと、なおさら長くなる。
- **対応**：行の長さを 120 に上げた（`pyproject.toml` の `[tool.ruff] line-length = 120`）。平易な日本語の説明を優先するための判断。
- **判断**：当初は 100（標準）にしていたが、平易な言葉を優先する方針で頻発したため 120 に変更した。

## L-004 生成物（STATUS.md）をコミットしてソースと一致を強制すると、作り直し忘れで検証が落ちる
- **状態**：ルール化済み（機械検査＝一致ゲートの撤去へ落とした。次の見直しで削除してよい・method.md の先例として当面残す）。
- **要点**：STATUS.md をコミットし、`work/` と一致するかをコミット前の検査・CI で突き合わせていた。`work/` を変えた後に `uv run status` を忘れると検証が落ちる摩擦が繰り返し起きた。「人が張り付かず仕組みで品質を担保する」狙いに反するノイズだった。
- **対応**：生成物なのでコミットしない方針に変えた（`.gitignore`・追跡から外す）。一致ゲート（コミット前フック・CI の `status --check`・`checks.py` の一致確認）を撤去。見たいときに `uv run status` で作り直す。
- **判断**：生成物を版管理してソースと同期させる仕掛けは「生成し忘れで落ちる」失敗を生むだけで正しさに寄与しない。ソースは常に `work/` の木であり、一覧はそこから機械的に導ける。撤去して摩擦を根本からなくした。

## L-005 Windows で git が改行を CRLF に変換する警告を出す（複数 OS で差分の原因になる）
- **要点**：Windows の作業コピーで改行が CRLF になり、Linux の CI と差分になりうる。
- **対応**：`.gitattributes` に `* text=auto eol=lf` を置き、改行を LF に統一。
- **設計への反映**：不要（テンプレートの標準装備として `.gitattributes` を含める）。

## L-007 業界標準（scikit-learn）があるのに評価メトリクス・標準化・CV 分割を自前で書いていた
- **状態**：ルール化済み（「標準ライブラリを再発明しない」を AGENTS のレビュー観点に落とした。先例として当面残す）。
- **要点**：roc_auc・accuracy・StandardScale・fold 分割を numpy で手書きしていた。これは業界標準の再発明で、保守負債・バグの温床だった（参考リポも全メトリクスを sklearn 実装）。
- **対応**：`scikit-learn` を ds の一級依存にし、eval のメトリクス・transforms.StandardScale・cv.make_folds を sklearn（accuracy_score/roc_auc_score・StandardScaler・KFold/StratifiedKFold）へ置換。置換後も既存テストが全通過＝手書きは純粋な再発明だった。モデルの具体・直列化の形式は注入して差し替え可能に保つ（sklearn→LightGBM の移行路は維持）。

## L-006 typer.Exit を console_script の起点で raise すると余計なエラー表示が出る
- **要点**：`[project.scripts]` の起点となる関数（typer.run を通さない）で `raise typer.Exit(1)` すると、捕捉されず余計なエラー表示（Traceback）が出る（終了コードは 1 で正しいが見苦しい）。
- **対応**：起点では `sys.exit(1)` を使う（task-lint・status・verify）。typer.run を通すコマンド（check）は typer.Exit のままでよい。
- **設計への反映**：不要（実装の作法）。自分たちで使って試す中で見つかった＝仕組みが働いている例。

## L-009 合否の判定を `<`/`>` の対で書くと NaN が両方 False で通過する（fail-open）
- **状態**：記録のみ（今回 `eval.passes` を修正。spec_lint／レビュー観点へのルール化候補）。
- **要点**：`if value < limit: return False` / `elif value > limit: return False` の形は、`value` が NaN のとき両方の比較が False になり、合格側へ**開いて**通ってしまう。発散モデルの `log_loss=nan`/`rmse=nan` が絶対条件を通り champion への採用まで届きうる（ds レビュー 2026-07-05）。
- **対応**：**合格条件を正の形で 1 度だけ書き、満たさなければ落とす**：`ok = value >= limit if higher_is_better else value <= limit; if not ok: return False`。NaN は「満たさない」に倒れて閉じる。
- **判断**：止める検査・合否・フィルタは既定を「不合格側」に置く（fail-closed）。同じ形の比較を他所（`store`/`schema`/`analysis`）で書くときも同様。2 回目が出たら機械検査へ。

## L-010 手書きのデータ検証は、ライブラリが吸収するエッジケースを落とす
- **状態**：記録のみ（「標準を再発明しない」の 2 回目の実例。pandera 導出の判断＝ISS-0010）。
- **要点**：`schema.validate` を手書きしていたため、parametrized dtype（`Datetime(...)`≠`"Datetime"`）・NaN が null 検査をすり抜ける・複合キー未検査・null 数で一意判定がぶれる、の 4 つを同時に落としていた（ds レビュー 2026-07-05）。これらは `pandera.polars` が既に正しく扱う領域。
- **対応**：今回は 4 穴を手書きのまま塞いだ（テスト付き）。ただし cross-column の `checks` 評価まで手で作り込むより、正本 YAML から pandera 実行器を導出する方が筋＝ISS-0010 で判断する。
- **判断**：L-007（メトリクス・CV 分割の手書き）に続く「標準の再発明」の 2 例目。検証器も『核は形式ライブラリを直接固定しない・実行器は正本からの導出物』の考え方を検証に広げるかを次に決める。

## L-011 「専用のリーク検出関数は作らない」方針を転換し、既存部品の合成 leakage_scan を追加
- **状態**：記録のみ（方針転換は即記録。転換の実装は T-0082・旧方針を書いた docstring も同時更新済み）。
- **要点**：correlations・category_target_summary・id_like・duplicate_columns を個別に読み合わせてリークを察する運用は見落としが出る。窓口 1 つ（`eda.leakage_scan`＝既存部品の合成のみ・新統計なし）へ転換し、怪しい列に理由を付けて返す。止める検査にはしない（値は事実・判断は実験側）。

## L-013 案内の書き忘れ（missing link）は一方向の doclint では捕まらない
- **状態**：ルール化済み（案内カバレッジ検査 coverage_lint を verify に接続。先例として当面残す）。
- **要点**：doclint は「書いた参照が実在するか」（dead link）だけを見る一方向の検査。逆向き＝新しい能力（CLI コマンド）が増えたのに、スキル/正本 docs に案内が書かれない（missing link）は機械で捕まらず、verify は緑のまま。実測で data の selectors・tuners・metrics（一覧コマンド）と issue の new（起票）がどのスキル/正本 docs からも到達不能だった（serve スキルに `data monitor` の 1 行が入ったのは作者が覚えていたから＝忘れても検査は落ちない）。
- **対応**：coverage_lint（cli.py 群を ast 解析して `@*.command` を全抽出→スキル/正本 docs での出現を検査・未到達＝error・免除は理由必須の allowlist）を PM_CHECKS に接続し、欠けていた案内を experiment/session スキルに追記して緑化。「部品は使える状態まで」の第 3 要件（スキル/雛形からの案内）の機械化。

## L-015 「同じ経路」は宣言でなく実測で確かめる（公式フックの走査対象が CI では空になりうる）
- **状態**：記録のみ（T-0100 で対処済み。同型の執行点を足すとき＝T-0101〜T-0103 の参照用）。
- **要点**：gitleaks の公式 pre-commit フックの entry は `gitleaks git --staged`＝**ステージ差分だけ**を走査する。CI のクリーンチェックアウト（差分ゼロ）で `pre-commit run gitleaks --all-files` を叩くと、緑だが**何も走査していない**（実測：ツリーに鍵を置いても Passed）。「ローカルと CI が同じ経路」はフック id の一致だけでは成立しない。
- **対応**：entry を作業ツリー全走査（`gitleaks dir .`＝実測 0.1 秒）に上書きし、ローカル・CI とも同じ走査にした。ドットファイル（`.env` 含む）は走査される（実測：`.env`/`.env.probe`/`.probedir/key.txt` すべて検出）。`.venv` 等がスキップされるのは gitleaks 既定の path allowlist による別機序で、ドット始まりだからではない（当初コメントの「ドット始まりは対象外」は誤り＝レビュー N-1 で訂正）。第二候補 detect-secrets は実測で results/ のデータ fingerprint（sha256 の内容ハッシュ）を偽陽性 7 件検出したため不採用。選定は両方とも**偽の鍵を仕込んだ検出デモ**で確かめた。
- **判断**：ガードレールの執行点を足すときは、(1) 止まるべき入力で本当に落ちる、(2) クリーンな状態で本当に通る、の両方を実測してから配線する（vacuous pass は fail-open と同じ）。配線の常在検査は tests/test_guardrails.py の型（ポリシー定数＋データ駆動）をコピーする。**走査モード自体もポリシー定数にして検査する**（`SECRETS_HOOK_ENTRY_PREFIX`＝entry が上流既定に戻ったら赤くする）：id 一致だけの配線テストは entry を消す変異で空振りに退行しても緑のまま通った（レビュー B-1・実測変異で確認）。
- **運用の注意（N-3）**：dir 走査は追跡外・ステージ外のファイルの鍵形文字列でもコミットを止める（想定外の driver は `.gitleaksignore`＝fingerprint 単位・理由必須で逃がす）。
- **settings の接頭辞 deny の限界（N-2）**：Claude Code の `Bash(...:*)` は**語境界つき**接頭辞一致なので、`git clean -f:*` は結合形 `clean -fd`/`-df`/`--force` を捕まえない（`-f` 直後が文字＝境界違反）。最頻の破壊形 `clean -fd` を素通しするため結合形も明示列挙した。フラグ後置（`git push origin --force`）は接頭辞一致の外＝hooks/sandbox の領分として T-0101 以降へ回す（settings だけでは覆えない）。

## L-016 依存監査は全部入り（--all-extras）で行う（部分監査は死角）
- **状態**：記録のみ（T-0102 で対処済み）。
- **要点**：エージェントが自律的に extra を足す運用では、入れている extra だけの監査は「まだ入れていない extra」の脆弱性を見逃す。CI の audit ジョブは `uv sync --all-extras` で同期したロック済み環境そのものを pip-audit で監査する（blocking・免除は `.pip-audit-ignore`＝理由必須。運用ルールの正本は workflow 内コメント）。
