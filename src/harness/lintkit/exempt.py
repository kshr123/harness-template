"""免除表の共有部品（lintkit）。理由必須・fail-closed（黙って免除しない）。

doc_source_lint・code_doc_lint・coverage_lint・boundary_lint が同じ「鍵 → 理由（空は不可）」の免除表検証を
個別に持っていた（`_validated_exempt`）。検証を `validate_exemptions` に 1 度だけ実装する。各検査は
`_EXEMPT` を dict のまま保ち（テストが monkeypatch で項目を差し込むため）検証だけを委譲する＝挙動不変。
"""

from __future__ import annotations

from collections.abc import Mapping


def validate_exemptions[K](owner: str, items: Mapping[K, str]) -> dict[K, str]:
    """免除表の理由が空でないことを確かめて dict を返す。空の理由は設定ミス＝即 ValueError（黙って免除しない）。

    メッセージは各検査が個別に出していた形をそのまま踏襲する（`_EXEMPT[{鍵!r}] の理由が空…（{owner}）`）＝
    移行しても既存テスト（`match="理由が空"`）が緑のまま＝挙動不変の証明になる。
    """
    for key, reason in items.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT[{key!r}] の理由が空。免除には人が読める理由が必須（{owner}）")
    return dict(items)
