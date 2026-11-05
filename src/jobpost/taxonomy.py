"""기준 목록(코드 + 이름): config/taxonomy/의 직무 분야·직무 유형·업종·스킬·고정 선택지를 읽고 검사한다.

규칙은 docs/taxonomy.md. 코드는 다시 쓰지 않고, 갈라지면 retired와 replaced_by를 남긴다. 데이터는 아직 legacy id로
저장돼 있어서(코드로 옮기기 전), 다른 모듈은 config.load("job_types"·"skills"·"profile"·"match_guide")로 예전 모양의
보기를 받는다. 보기는 이 모듈이 만들고, 원본은 config/taxonomy/ 한 곳이다.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

DIR = Path(__file__).resolve().parents[2] / "config" / "taxonomy"

CODE_RE = {
    "field": re.compile(r"JF\d{2}"),
    "type": re.compile(r"JT\d{3}"),
    "industry_group": re.compile(r"IN\d{2}"),
    "industry": re.compile(r"IN\d{4}"),
    "skill": re.compile(r"SK\d{4}"),
    "skill_group": re.compile(r"SG\d{2}"),
    "interchangeable": re.compile(r"IS\d{2}"),
    "enum": re.compile(r"[A-Z]{2}\d{2}"),
}


class TaxonomyError(ValueError):
    pass


@cache
def raw(name: str) -> dict[str, Any]:
    with (DIR / f"{name}.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _active(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for x in items if not x.get("retired")]


# ---------- 목록 ----------

def fields() -> list[dict[str, Any]]:
    return raw("jobs")["fields"]


def job_types() -> list[dict[str, Any]]:
    return raw("jobs")["types"]


def industry_groups() -> list[dict[str, Any]]:
    return raw("industries")["groups"]


def industries() -> list[dict[str, Any]]:
    """중분류(판정·저장 단위). 각 항목에 group(대분류 코드)을 붙인다."""
    return [{**it, "group": g["code"]} for g in industry_groups() for it in g.get("items") or []]


def skills() -> list[dict[str, Any]]:
    return raw("skills")["skills"]


def enum(key: str) -> list[dict[str, Any]]:
    return raw("enums")[key]


def names(key: str) -> list[str]:
    """고정 선택지 이름 목록(지금 데이터·지시문에 쓰는 값)."""
    return [x["name"] for x in _active(enum(key))]


# ---------- 검사 ----------

def validate() -> None:
    """코드 형식·중복, 상위·관계 코드가 있는지, replaced_by가 있는 코드를 가리키는지. 틀리면 TaxonomyError."""
    seen: dict[str, str] = {}

    def add(code: str, kind: str, where: str) -> None:
        if not CODE_RE[kind].fullmatch(code or ""):
            raise TaxonomyError(f"{where}: 코드 형식이 틀림 {code!r}({kind})")
        if code in seen:
            raise TaxonomyError(f"{where}: 코드 {code}가 겹침({seen[code]})")
        seen[code] = where

    for f in fields():
        add(f["code"], "field", "jobs.fields")
    for t in job_types():
        add(t["code"], "type", "jobs.types")
        if t.get("field") not in {f["code"] for f in fields()}:
            raise TaxonomyError(f"jobs.types {t['code']}: 없는 분야 {t.get('field')}")
    for g in industry_groups():
        add(g["code"], "industry_group", "industries.groups")
        for it in g.get("items") or []:
            add(it["code"], "industry", "industries.items")
            if not it["code"].startswith(g["code"]):
                raise TaxonomyError(f"industries {it['code']}: 대분류 {g['code']}로 시작해야 함")
    for g in raw("skills")["groups"]:
        add(g["code"], "skill_group", "skills.groups")
    group_codes = {g["code"] for g in raw("skills")["groups"]}
    for s in skills():
        add(s["code"], "skill", "skills.skills")
        if not set(s.get("groups") or []) <= group_codes:
            raise TaxonomyError(f"skills {s['code']}: 없는 묶음 {s.get('groups')}")
    skill_codes = {s["code"] for s in skills()}
    for s in skills():
        if s.get("broader") and s["broader"] not in skill_codes:
            raise TaxonomyError(f"skills {s['code']}: 없는 넓은 개념 {s['broader']}")
    for i in raw("skills").get("interchangeable") or []:
        add(i["code"], "interchangeable", "skills.interchangeable")
        if not set(i["members"]) <= skill_codes:
            raise TaxonomyError(f"skills {i['code']}: 없는 스킬 {set(i['members']) - skill_codes}")
    for key, items in raw("enums").items():
        prefixes = {x["code"][:2] for x in items}
        if len(prefixes) != 1:
            raise TaxonomyError(f"enums.{key}: 한 목록은 한 접두어 {prefixes}")
        for x in items:
            add(x["code"], "enum", f"enums.{key}")
    for item in [*fields(), *job_types(), *industries(), *skills()]:
        for r in item.get("replaced_by") or []:
            if r not in seen:
                raise TaxonomyError(f"{item['code']}: replaced_by {r} 없음")
    prefixes = [p for it in industries() for p in it.get("ksic") or []] + list(raw("industries").get("ksic_generic") or [])
    dup = {p for p in prefixes if prefixes.count(p) > 1}
    if dup:
        raise TaxonomyError(f"industries: KSIC 앞자리가 두 곳에 있음 {sorted(dup)}")
    words = [w.rstrip("*").lower() for x in [*industry_groups(), *industries()] for w in x.get("words") or []]
    dupw = {w for w in words if words.count(w) > 1}
    if dupw:
        raise TaxonomyError(f"industries: words가 두 곳에 있음 {sorted(dupw)}")
    legacy = [x["legacy"] for x in [*fields(), *job_types(), *industries()] if x.get("legacy")]
    if len(legacy) != len(set(legacy)):
        raise TaxonomyError("지난 id(직무·업종)가 겹침")


# ---------- KSIC → 업종 ----------

def industry_from_ksic(ksic: str | None) -> tuple[str | None, str]:
    """DART 업종 코드(KSIC) → (업종 중분류 코드 또는 None, 까닭). 긴 앞자리가 먼저.
    까닭: 'ksic'(대응표로 정함) · 'generic'(도메인을 알려 주지 않는 코드, 공고 정리로) · 'unmapped'(대응표에 없음) · 'none'."""
    if not ksic:
        return None, "none"
    k = str(ksic)
    pairs = [(p, it["code"]) for it in _active(industries()) for p in it.get("ksic") or []]
    pairs += [(p, None) for p in raw("industries").get("ksic_generic") or []]
    for p, code in sorted(pairs, key=lambda x: -len(x[0])):
        if k.startswith(p):
            # 코드가 앞자리보다 짧아 그 아래에 다른 업종(또는 generic)이 있으면 정하지 않는다(예: 649 지주회사 포함)
            below = {c for q, c in pairs if len(q) > len(k) and q.startswith(k)}
            if below - {code}:
                return None, "generic"
            return (code, "ksic") if code else (None, "generic")
    if any(q.startswith(k) for q, _ in pairs):  # 대응표 앞자리보다 짧은 코드(예: 66)
        return None, "generic"
    return None, "unmapped"


# ---------- 업종 경험 판정 ----------

def industry_code(x: str | None) -> str | None:
    """업종 코드(대·중분류) 또는 지난 id → 코드."""
    if not x:
        return None
    if CODE_RE["industry"].fullmatch(x) or CODE_RE["industry_group"].fullmatch(x):
        return x
    return code_of(x)


def industry_name(x: str | None) -> str:
    code = industry_code(x)
    for it in [*industry_groups(), *industries()]:
        if it["code"] == code:
            return it["name"]
    return x or ""


def industry_fit(need: str | None, have: set[str]) -> float:
    """공고가 요구한 업종(대분류 또는 중분류)과 지원자 경력 업종(중분류) → 1 충족 · 0.5 일부(같은 대분류) · 0."""
    n = industry_code(need)
    mine = {c for c in (industry_code(h) for h in have) if c}
    if not n:
        return 1.0
    if len(n) == 4:  # 대분류 요구: 그 아래 아무거나
        return 1.0 if any(c.startswith(n) for c in mine) else 0.0
    if n in mine:
        return 1.0
    return 0.5 if any(c[:4] == n[:4] for c in mine) else 0.0


# ---------- 업종 경험 문장 → 업종 코드(맞출 사전 words) ----------

# 넓은 말(*) 뒤: 바로 산업·분야 등이 오거나, '공공·금융·국방 분야'처럼 나열 뒤에 온다
CTX = r"(?=(?:\s*[·,/ㆍ]\s*[가-힣A-Za-z]{1,10})*\s*(?:산업|업(?:계|권|종|체)?(?![가-힣])|도메인|분야|기업|기관|회사|사(?![가-힣])|펌|서비스|프로젝트|플랫폼))"  # *가 붙은 말 뒤에 와야 하는 말


@cache
def _word_patterns() -> list[tuple[re.Pattern[str], str, str]]:
    out = []
    for x in [*industry_groups(), *_active(industries())]:
        for w in x.get("words") or []:
            ctx = w.endswith("*")
            word = w.rstrip("*")
            body = r"\s*".join(re.escape(part) for part in word.split())
            if word.isascii():  # 영문은 단어 단위로(WSI 안의 SI는 세지 않음)
                body = r"(?<![A-Za-z])" + body + r"(?![A-Za-z])"
            else:  # 한글은 말 앞에 다른 글자가 붙지 않을 때만(강화학습 안의 화학은 세지 않음)
                body = r"(?<![가-힣])" + body
            out.append((re.compile(body + (CTX if ctx else ""), re.I), x["code"], word))
    return sorted(out, key=lambda p: -len(p[2]))


def industries_in(text: str) -> list[str]:
    """업종 경험 문장 속 업종 코드(긴 말부터, 찾은 말은 지워 겹쳐 세지 않음). 대분류가 있으면 그 아래 중분류는 뺀다."""
    found: list[str] = []
    rest = text or ""
    for pat, code, _ in _word_patterns():
        if pat.search(rest):
            found.append(code)
            rest = pat.sub("가", rest)  # 지운 자리는 글자 하나로(나열 '공공·금융·국방 분야'이 이어지게)
    found = list(dict.fromkeys(found))
    groups = {c for c in found if len(c) == 4}
    return [c for c in found if not (len(c) == 6 and c[:4] in groups)]


# ---------- 지난 id ↔ 코드 ----------

def code_of(legacy: str | None) -> str | None:
    """저장된 지난 id(직무 유형·분야·업종) → 코드. 모르면 None."""
    if not legacy:
        return None
    legacy = raw("jobs").get("legacy_aliases", {}).get(legacy, legacy)
    for x in [*fields(), *job_types(), *industries()]:
        if x.get("legacy") == legacy:
            return x["code"]
    return None


# ---------- 예전 모양 보기(코드로 옮기기 전까지 다른 모듈이 읽는 것) ----------

@cache
def job_types_view() -> dict[str, Any]:
    """jobtypes.py가 읽는 모양: 데이터·AI 직무 유형(family data) + 그 밖의 직무 분야(family other), id는 legacy."""
    j = raw("jobs")
    types = [{"id": t["legacy"], "code": t["code"], "name": t["name"], "short": t.get("short", t["name"]),
              "desc": t["desc"], **({"direction": False} if t.get("direction") is False else {}),
              **({"family": "other"} if t.get("field") != "JF01" else {})}  # 계열은 분야로 정한다
             for t in _active(job_types())]
    types += [{"id": f["legacy"], "code": f["code"], "name": f["name"], "short": f.get("short", f["name"]),
               "family": "other", "direction": False, "desc": f["desc"]}
              for f in _active(fields()) if f["code"] != "JF01"]
    return {"version": j["version"], "field": fields()[0]["name"], "legacy": j.get("legacy_aliases") or {},
            "types": types}


@cache
def skills_view() -> dict[str, Any]:
    """matching.py가 읽는 모양: {묶음 이름: [{name, aliases, code}]}, interchangeable: [[이름]]."""
    s = raw("skills")
    by_code = {x["code"]: x for x in skills()}
    groups: dict[str, list[dict[str, Any]]] = {g["name"]: [] for g in s["groups"]}
    gname = {g["code"]: g["name"] for g in s["groups"]}
    for x in _active(skills()):
        for g in x.get("groups") or []:
            groups[gname[g]].append({"name": x["name"], "aliases": x.get("aliases") or [], "code": x["code"]})
    return {"version": s["version"], "groups": groups,
            "interchangeable": [[by_code[m]["name"] for m in i["members"]] for i in s.get("interchangeable") or []],
            "stopwords": s.get("stopwords") or []}


def profile_extras() -> dict[str, Any]:
    """profile.yaml에 합치는 목록: 업종(id는 legacy), 숙련도·역할·학력·전공·영어·원하는 직급."""
    return {
        "version": raw("industries")["version"],
        "industries": [{"id": x["legacy"], "name": x["name"], "code": x["code"]} for x in _active(industries())],
        "skill_levels": [{"level": x["level"], "name": x["name"], "desc": x["desc"]} for x in enum("skill_levels")],
        "project_parts": names("project_parts"),
        "degrees": names("degrees"),
        "major_groups": names("major_groups"),
        "english": names("english_levels"),
        "english_low": [x["name"] for x in enum("english_levels") if x.get("low")],
        "want_levels": names("want_levels"),
    }


def match_guide_extras() -> dict[str, Any]:
    return {"item_kinds": names("item_kinds"),
            "posting_facts": {"level": names("match_levels"), "english": names("match_english"),
                              "employment": names("match_employment")}}
