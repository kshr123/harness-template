"""deliver プロファイル — 作業単位の木を、クライアントに見せる WBS・ガントとして出す。

日程の正本は `work/` の作業単位の frontmatter ひとつ（階層は「親はフォルダ」の既存原則、予定日・工数・
節目は EP-43 で入れた Item のフィールド、状態・実績は status と created/closed から導出）。このプロファイルは
その木を顧客向けに射影するだけで、日程の第 2 の台帳を持たない。案件固有の上書き（カレンダー・顧客向けの
節構成・`work/` に置けない手動行）だけが `docs/wbs.yaml` に載る。

使い方の正本は `docs/deliver.md`。中核へは `.harness/config.toml` の profiles 経由で PROFILE（検査の結線）
だけを見せる。PROFILE の取り込みは軽い（holidays・fastapi・openpyxl をここから import しない）。
重い依存は使う場所（祝日は calendar.py の関数内・編集サーバは cli.py のコマンド内）に閉じる。
"""

from harness.deliver.profile import PROFILE

__all__ = ["PROFILE"]
