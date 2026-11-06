"""개인 필터(1차 필터). 저장된 공고는 그대로 두고 보는 목록에서만 거른다.
화면 쪽 같은 규칙은 web/src/lib/filter.ts. 걸린 이유(reasons)는 아침 알림의 필터 밖 새 공고에 쓴다."""

from __future__ import annotations

from typing import Any

from .models import CompanyType


def reasons(
    *,
    title: str,
    company: str,
    company_type: CompanyType,
    career_min: int | None,
    career_max: int | None,
    regions: list[str],
    filters: dict[str, Any],
    job_type: str | None = None,
    employment: list[str] | None = None,
    job_type2: str | None = None,
    duty_jobs: list[str] | None = None,
) -> list[tuple[str, str]]:
    """걸린 이유(통과면 빈 목록). (종류, 값): keyword 제외 키워드, company 제외 회사, job 직무 유형 id,
    duty 업무가 다른 분야, company_type 기업 구분, career 경력, region 지역, employment 고용 형태. 제외 키워드·회사에 걸리면 그것만, 아니면 걸린 조건 전부.
    제외에 안 걸리고 항상 보여줄 회사면 통과."""
    out = [("keyword", kw) for kw in filters.get("exclude_keywords") or [] if kw.replace(" ", "") in title.replace(" ", "")]
    out += [("company", c) for c in filters.get("exclude_companies") or [] if c and c in company]
    if out:
        return out
    if any(c and c in company for c in filters.get("always_companies") or []):
        return []

    # 직무 유형이 아직 분류되지 않은 공고(오늘 새로 들어와 AI가 못 본 것)는 통과시킨다
    allowed_jobs = filters.get("job_types")
    # 보조 직무 유형(job_type2, 데이터·AI 일이 큰 그 밖 공고)이 맞아도 통과
    if allowed_jobs and job_type and job_type not in allowed_jobs and job_type2 not in allowed_jobs:
        out.append(("job", job_type))
    # 직무 유형은 맞아도 공고 정리의 업무가 모두 내 직무·가까운 직무 밖이면 내 분야가 아니다(2026-11-06).
    # duty_jobs: 이 공고를 내 분야로 보는 직무 유형들(screen.duty_jobs). 공고 정리가 없으면 None이라 통과
    elif allowed_jobs and duty_jobs and not set(duty_jobs) & set(allowed_jobs):
        out.append(("duty", ""))

    allowed_types = filters.get("company_types")
    if allowed_types and company_type.value not in allowed_types:
        out.append(("company_type", company_type.value))

    career = filters.get("career") or {}
    fmin, fmax = career.get("min"), career.get("max")
    lo = career_min or 0
    hi = career_max if career_max is not None else 99
    if (fmin is not None and hi < fmin) or (fmax is not None and lo > fmax):
        out.append(("career", ""))

    allowed_regions = filters.get("regions")
    if allowed_regions and regions:
        remote_ok = "원격" in allowed_regions and any(w in title for w in ("재택", "원격", "리모트"))
        if not remote_ok and not any(any(a in r for a in allowed_regions) for r in regions):
            out.append(("region", ", ".join(regions)))

    # 고용 형태: "인턴직"·"정규직(수습)"처럼 붙어 오는 표기가 있어 포함으로 본다. 정보가 없으면 통과
    allowed_emp = filters.get("employment_types")
    if allowed_emp and employment and not any(a in e for e in employment for a in allowed_emp):
        out.append(("employment", ", ".join(employment)))
    return out


def passes(**kw: Any) -> tuple[bool, str | None]:
    """(통과 여부, 처음 걸린 이유의 종류)."""
    r = reasons(**kw)
    return (not r, r[0][0] if r else None)
