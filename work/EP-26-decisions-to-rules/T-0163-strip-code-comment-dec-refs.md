---
id: T-0163
kind: task
status: done
title: src/tests のコードコメントから DEC 短縮参照を一掃＋template-copy の How-to 改善を取り込む
created: 2026-07-07
depends_on: [T-0162]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0163 src/tests のコードコメント DEC 参照を一掃

EP-26 で docs から DEC を撤去したが、src/・tests/ のコメント/docstring に DEC 短縮参照（例「（プロファイル
境界・DEC-0004）」）が約 120 箇所残っていた。設計理由は本文のルール（AGENTS/method）に生きているので、
コメントの DEC 番号だけ除去し必要な語は残す（正規表現で除去＋掃除・空白は潰さない＝文字列リテラルの
YAML インデントを壊さない・中途の助詞欠けは手で修正）。ruff format 後 verify 緑。docs/archive/（日付記録）は
歴史なので触らない。あわせて別ターミナルの template-copy How-to 改善（fffce53：履歴の語り・タスクID参照の
除去）を origin/main 側へ取り込み、分岐を解消（decisions/ 参照の除去は EP-26 側を維持）。
