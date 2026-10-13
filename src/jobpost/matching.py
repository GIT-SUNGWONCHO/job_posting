"""매칭 점수(v1). 계산법은 config/matching.yaml, 스킬 사전은 config/skills.yaml.

점수는 AI 없이 규칙으로만 낸다(같은 입력이면 늘 같은 점수). 매칭 이유 문장은 따로 AI가 쓴다.
"""

from __future__ import annotations

import re
from datetime import date
from functools import cache
from typing import Any

from . import config


@cache
def _skill_patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for items in config.load("skills")["groups"].values():
        for item in items:
            for alias in [item["name"], *(item.get("aliases") or [])]:
                if re.search(r"[가-힣]", alias):
                    pat = re.compile(re.escape(alias))
                else:
                    flags = 0 if len(alias) <= 3 else re.IGNORECASE
                    pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", flags)
                out.append((item["name"], pat))
    return out


def extract_skills(text: str) -> set[str]:
    """글에서 사전에 있는 스킬을 찾아 대표 이름으로 돌려준다."""
    found: set[str] = set()
    for name, pat in _skill_patterns():
        if name not in found and pat.search(text or ""):
            found.add(name)
    return found


def _collapse(skills: set[str]) -> dict[str, set[str]]:
    """{세는 단위: 스킬들}. 바꿔 쓸 수 있는 묶음은 하나로 센다."""
    groups = [set(g) for g in config.load("skills").get("interchangeable") or []]
    units: dict[str, set[str]] = {}
    for s in skills:
        g = next((g for g in groups if s in g), None)
        key = "/".join(sorted(g)) if g else s
        units.setdefault(key, set()).add(s)
    return units


def canonical_skills(skills: list[str]) -> set[str]:
    """프로필에 적은 스킬을 사전 이름으로 바꾼다. 사전에 없는 건 버린다(사전에 추가할 후보)."""
    out: set[str] = set()
    for s in skills:
        out |= extract_skills(s)
    return out


def career_years(start: str, today: date) -> int | None:
    """경력 시작(YYYY-MM)부터 햇수(반올림). 화면 profile.ts careerYears와 같다."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", start or "")
    if not m:
        return None
    months = (today.year - int(m.group(1))) * 12 + (today.month - int(m.group(2)))
    return None if months < 0 else round(months / 12)


def score(profile: dict[str, Any], posting: dict[str, Any], posting_skills: set[str] | None,
          today: date) -> dict[str, Any]:
    """posting은 화면용 파일의 공고 한 건. posting_skills가 None이면 본문이 없는 공고."""
    cfg = config.load("matching")
    w = cfg["weights"]

    targets = set(profile.get("targetRoles") or []) | ({profile["currentRole"]} if profile.get("currentRole") else set())
    jt = posting.get("jobType")
    related = {r for t in targets for r in (cfg["related"].get(t) or [])}
    if not jt:
        job = w["job"] * cfg["unknown_job_ratio"]
    elif jt in targets:
        job = w["job"]
    elif jt in related:
        job = w["job"] / 2
    else:
        job = 0.0

    years = career_years(profile.get("careerStart", ""), today)
    lo, hi = posting.get("careerMin") or 0, posting.get("careerMax")
    if years is None:
        career = w["career"] * cfg["unknown_career_ratio"]
    elif years < lo:
        career = max(0.0, w["career"] - cfg["career_short_penalty"] * (lo - years))
    elif hi is not None and years > hi:
        career = max(0.0, w["career"] - cfg["career_over_penalty"] * (years - hi))
    else:
        career = float(w["career"])

    mine = canonical_skills(profile.get("skills") or [])
    if not posting_skills:
        skills = w["skills"] * cfg["unknown_skills_ratio"]
        matched: list[str] = []
        missing: list[str] = []
    else:
        groups = [set(g) for g in config.load("skills").get("interchangeable") or []]
        units = _collapse(posting_skills)
        matched, missing = [], []
        hit = 0
        for members in units.values():
            group = next((g for g in groups if members & g), None)
            mine_here = (mine & group) if group else (mine & members)
            if mine_here:
                hit += 1
                matched += sorted(mine_here & members) or sorted(mine_here)
            else:
                missing += sorted(members)
        matched, missing = sorted(set(matched)), sorted(set(missing))
        denom = max(min(len(units), cfg["skill_denominator"]), cfg.get("skill_min_denominator", 1))
        skills = w["skills"] * min(1.0, hit / denom)

    return {
        "score": round(job + career + skills),
        "parts": {"job": round(job), "career": round(career), "skills": round(skills)},
        "matched": matched,
        "missing": missing,
        "v": cfg["version"],
        "skills_v": config.load("skills")["version"],
    }
