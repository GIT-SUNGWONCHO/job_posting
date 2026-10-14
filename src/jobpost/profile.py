"""프로필 v2: 경력(회사) > 직무 구간 > 프로젝트, 스킬 숙련도 1~4(형식은 web/src/lib/profile.ts와 같다).

직무가 바뀌면 직무 구간을 새 칸으로 적는다(비중은 없다). 직무별 연수와 데이터 경력 합은 입력하지 않고 기간으로 계산한다.
AI에는 회사명까지 보내고 이름·연락처는 보내지 않는다(docs/decisions.md 2026-10-14 매칭).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import config

NON_DATA_ROLES = {"pi", "sales_md"}


def _month(s: str | None) -> int | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", s or "")
    return int(m.group(1)) * 12 + int(m.group(2)) - 1 if m else None


def months(start: str | None, end: str | None, today: date) -> int:
    """시작 달부터 끝 달까지(끝 달 포함). 끝이 비면 오늘까지."""
    a = _month(start)
    b = _month(end) if end else today.year * 12 + today.month - 1
    return max(0, b - a + 1) if a is not None and b is not None else 0


def roles() -> dict[str, str]:
    return {r["id"]: r["name"] for r in config.load("profile")["roles"]}


def role_name(r: dict[str, Any]) -> str:
    return (r.get("roleName") or "").strip() if r.get("role") == "other" else roles().get(r.get("role", ""), r.get("role", ""))


def is_v2(data: dict[str, Any]) -> bool:
    return data.get("schema") == 2


def role_years(data: dict[str, Any], today: date) -> dict[str, float]:
    """직무 이름별 연수. 직무 구간이 없는 경력은 '직무 미입력'으로 센다."""
    out: dict[str, float] = {}
    for c in data.get("careers") or []:
        rs = c.get("roles") or []
        if not rs:
            out["직무 미입력"] = out.get("직무 미입력", 0) + months(c.get("start"), c.get("end"), today) / 12
        for r in rs:
            name = role_name(r) or "직무 미입력"
            out[name] = out.get(name, 0) + months(r.get("start"), r.get("end"), today) / 12
    return out


def career_totals(data: dict[str, Any], today: date) -> tuple[float, float]:
    """(총 경력, 데이터·AI 경력) 연수. 데이터가 아닌 직무(PI 기획, 영업·MD)는 데이터 경력에서 뺀다."""
    total = sum(months(c.get("start"), c.get("end"), today) for c in data.get("careers") or []) / 12
    non_data = sum(months(r.get("start"), r.get("end"), today)
                   for c in data.get("careers") or [] for r in c.get("roles") or []
                   if r.get("role") in NON_DATA_ROLES) / 12
    return total, max(0.0, total - non_data)


def career_start(data: dict[str, Any]) -> str:
    starts = [c.get("start") for c in data.get("careers") or [] if _month(c.get("start")) is not None]
    return min(starts) if starts else ""


def latest_role(data: dict[str, Any]) -> str:
    rs = [r for c in data.get("careers") or [] for r in c.get("roles") or []]
    rs.sort(key=lambda r: (not r.get("end"), r.get("end") or "", r.get("start") or ""))
    return rs[-1].get("role", "") if rs else ""


def rule_view(data: dict[str, Any]) -> dict[str, Any]:
    """규칙 점수(matching.py)가 읽는 v1 모양. 비교용으로만 남긴다."""
    if not is_v2(data):
        return data
    return {"careerStart": career_start(data), "currentRole": latest_role(data),
            "targetRoles": data.get("targetRoles") or [], "skills": [s["name"] for s in data.get("skills") or []]}


def has_content(data: dict[str, Any]) -> bool:
    if is_v2(data):
        return bool(data.get("careers") or data.get("skills"))
    return bool(data.get("skills") or data.get("currentRole") or data.get("targetRoles"))


def _period(x: dict[str, Any]) -> str:
    return f"{(x.get('start') or '?').replace('-', '.')}~{(x.get('end') or '현재').replace('-', '.')}"


def text(data: dict[str, Any], today: date) -> str:
    """AI에 보내는 지원자 요약. 회사명까지 넣는다."""
    cfg = config.load("profile")
    inds = {i["id"]: i["name"] for i in cfg["industries"]}
    levels = {lv["level"]: lv["name"] for lv in cfg["skill_levels"]}
    total, data_years = career_totals(data, today)
    lines = [f"총 경력 약 {total:.1f}년, 그중 데이터·AI 경력 약 {data_years:.1f}년"]
    ry = role_years(data, today)
    if ry:
        lines.append("직무별 경력: " + ", ".join(f"{k} {v:.1f}년" for k, v in sorted(ry.items(), key=lambda x: -x[1])))
    if data.get("targetRoles"):
        lines.append("희망 직무: " + ", ".join(roles().get(r, r) for r in data["targetRoles"]))
    lines.append("[경력]")
    for c in sorted(data.get("careers") or [], key=lambda c: c.get("start") or "", reverse=True):
        title = f", {c['title']}" if c.get("title") else ""
        lines.append(f"- {c.get('company', '')} ({inds.get(c.get('industry', ''), '업종 미입력')}) {_period(c)}{title}")
        for r in sorted(c.get("roles") or [], key=lambda r: r.get("start") or "", reverse=True):
            summary = f" — {r['summary']}" if r.get("summary") else ""
            lines.append(f"  - 직무: {role_name(r)} {_period(r)}{summary}")
            for pj in r.get("projects") or []:
                part = f", {pj['part']}" if pj.get("part") else ""
                skills = f" [스킬: {', '.join(pj['skills'])}]" if pj.get("skills") else ""
                result = f" — {pj['summary']}" if pj.get("summary") else ""
                lines.append(f"    - 프로젝트: {pj.get('title', '')} ({_period(pj)}{part}){result}{skills}")
    if data.get("skills"):
        lines.append("[스킬(숙련도 1~4)] " + ", ".join(
            f"{s['name']}({s.get('level', '?')} {levels.get(s.get('level'), '')})".replace(" )", ")")
            for s in sorted(data["skills"], key=lambda s: -(s.get("level") or 0))))
    edu = data.get("education") or {}
    if edu.get("degree") or edu.get("major"):
        lines.append(f"[학력] {edu.get('degree', '')} {edu.get('major', '')} ({edu.get('majorGroup', '')})".strip())
    if data.get("certs"):
        lines.append("[자격증] " + ", ".join(f"{x['name']}({x['year']})" if x.get("year") else x["name"] for x in data["certs"]))
    if data.get("english"):
        lines.append(f"[영어] {data['english']}")
    return "\n".join(lines)
