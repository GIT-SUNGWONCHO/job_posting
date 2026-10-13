"""수집처별 수집기. 각 수집기는 Posting 목록과 수집 결과 요약을 돌려준다."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Posting


@dataclass
class CollectResult:
    source: str
    postings: list[Posting] = field(default_factory=list)
    complete: bool = True  # 끝까지 받았는지. False면 이번에 안 보인 공고를 마감으로 보지 않는다
    errors: list[str] = field(default_factory=list)
    requests: int = 0
    # 수집처가 붙인 기업 구분: 회사 키 -> 구분 목록
    company_types: dict[str, set[str]] = field(default_factory=dict)
