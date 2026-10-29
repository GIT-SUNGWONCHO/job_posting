"""수집한 공고를 담는 공통 형식. 모든 수집처는 이 형식으로 바꿔서 넘긴다."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Source(StrEnum):
    ZIGHANG = "zighang"
    REMEMBER = "remember"
    SARAMIN = "saramin"
    WANTED = "wanted"


class DeadlineType(StrEnum):
    DATE = "date"  # 마감일이 있음
    ALWAYS = "always"  # 상시
    UNTIL_FILLED = "until_filled"  # 채용 시 마감


class CompanyType(StrEnum):
    LARGE = "대기업"
    PUBLIC = "공기업·공공기관"
    FOREIGN = "외국계"
    OTHER = "그 외"


class Posting(BaseModel):
    """수집처 한 곳의 공고 한 건."""

    source: Source
    source_id: str
    url: str
    via: str | None = None  # 직행이 다른 플랫폼에서 가져온 공고면 그 플랫폼 이름
    apply_url: str | None = None

    company: str
    title: str

    career_min: int | None = None  # 년. None은 하한 없음
    career_max: int | None = None  # 년. None은 상한 없음
    newcomer: bool = False  # 신입 지원 가능

    deadline_type: DeadlineType = DeadlineType.UNTIL_FILLED
    deadline: date | None = None

    regions: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)  # 수집처의 직무 분류 그대로
    keywords: list[str] = Field(default_factory=list)

    source_company_types: list[str] = Field(default_factory=list)  # 수집처가 붙인 기업 구분
    headhunter: bool = False
    posted_at: datetime | None = None

    description: str | None = None  # 공고 본문(있는 수집처만)
    raw: dict[str, Any] | None = None  # 수집처 원본. 분류 기준이 바뀌면 이걸로 재처리한다

    @property
    def uid(self) -> str:
        return f"{self.source.value}:{self.source_id}"


class Detail(BaseModel):
    """목록과 따로 받는 공고 상세(본문 등)."""

    uid: str
    fetched_at: datetime
    description: str | None = None
    apply_url: str | None = None
    related_ids: list[str] = Field(default_factory=list)  # 수집처가 같은 공고로 묶은 다른 id
    raw: dict[str, Any] | None = None
