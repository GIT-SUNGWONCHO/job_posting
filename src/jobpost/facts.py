"""공고 정리: 본문에 글로만 있는 매칭 항목(핵심 업무, 필수·우대 스킬, 연수 요건, 직급, 도메인, 학력, 어학 등)을
AI가 공고당 한 번 뽑아 data 폴더 facts.jsonl에 둔다. 공고의 것이라 모든 사람이 함께 쓴다.

적힌 것만 뽑고 추측하지 않는다. 지시문을 바꾸면 PROMPT_VERSION을 올린다(다시 뽑는다).
어느 공고부터 뽑을지는 사람마다 개인 필터를 통과한 공고(후보)의 합집합이다(docs/decisions.md 2026-10-14 매칭).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from . import bodyread, config, jobtypes, matching, recommend, taxonomy

log = logging.getLogger(__name__)

PROMPT_VERSION = 6  # (업종 사전·코드 규칙은 저장된 문장으로 다시 계산해 버전을 올리지 않는다, words_hash) 6: 회사 도메인을 이름으로 고름. 3~5(2026-11-05): 회사 도메인(코드)과 업종 경험 문장을 나눔. 5: AI는 문장만, 업종·필수/우대는 코드(사전·제목). 2(2026-11-03): 업무마다 일의 종류(직무 유형)·책임 범위, 사람 관리, 연수 상한, 고용 형태·기간, 영어 쓰는 곳
BODY_CHARS = 3500  # 자격요건·우대사항은 본문 뒤쪽에 있어서 넉넉히 보낸다
FILE = "facts.jsonl"

# 고정 선택지(코드 + 이름)는 config/taxonomy/enums.yaml. 여기서는 이름을 쓴다(지시문·저장 값)
LEVELS = taxonomy.names("posting_levels")
DEGREES = taxonomy.names("posting_degrees")
NEEDS = taxonomy.names("needs")
WORK = taxonomy.names("work_modes")
MANAGES = taxonomy.names("manages")
SCOPES = taxonomy.names("scopes")  # 업무마다 책임 범위(직무와 상관없이 쓰는 말)
EMPLOYMENT = taxonomy.names("employment")
ENGLISH_USES = taxonomy.names("english_uses")


def industries() -> dict[str, str]:
    return {i["id"]: i["name"] for i in config.load("profile")["industries"]}


def _domain_names() -> dict[str, str]:
    """회사 도메인 선택지: 업종 중분류 이름 → 코드. AI에는 이름으로 고르게 하고(지시문에 목록을 따로 싣지 않아도 됨) 코드로 바꿔 저장."""
    return {i["name"]: i["code"] for i in taxonomy.industries() if not i.get("retired")}


def words_hash() -> str:
    """업종 사전(words)과 규칙 버전. 바뀌면 저장된 문장으로 업종 경험을 AI 없이 다시 계산한다."""
    words = [(x["code"], x.get("words") or []) for x in [*taxonomy.industry_groups(), *taxonomy.industries()]]
    return hashlib.sha1(json.dumps([RULES_V, words], ensure_ascii=False).encode()).hexdigest()[:10]


def schema() -> dict[str, Any]:
    kinds = [t["id"] for t in jobtypes.taxonomy()["types"]]
    strings = {"type": "ARRAY", "items": {"type": "STRING"}}
    return {"type": "OBJECT", "required": ["level", "manages", "duties", "required_skills", "preferred_skills", "years",
                                           "company_domain", "domain_quotes", "degree", "majors", "certs",
                                           "english", "employment", "work_mode"],
            "properties": {
                "level": {"type": "STRING", "enum": LEVELS},
                "manages": {"type": "STRING", "enum": MANAGES},
                "duties": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["text", "kind", "scope"], "properties": {
                    "text": {"type": "STRING"}, "kind": {"type": "STRING", "enum": kinds},
                    "scope": {"type": "STRING", "enum": SCOPES}}}},
                "required_skills": strings,
                "preferred_skills": strings,
                "years": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["area", "min"], "properties": {
                    "area": {"type": "STRING"}, "min": {"type": "INTEGER"}, "max": {"type": "INTEGER"}}}},
                "company_domain": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(_domain_names())}},
                "domain_quotes": strings,
                "degree": {"type": "STRING", "enum": DEGREES},
                "majors": strings,
                "major_need": {"type": "STRING", "enum": NEEDS},
                "certs": strings,
                "english": {"type": "OBJECT", "required": ["need"], "properties": {
                    "need": {"type": "STRING", "enum": NEEDS},
                    "uses": {"type": "ARRAY", "items": {"type": "STRING", "enum": ENGLISH_USES}}}},
                "employment": {"type": "STRING", "enum": EMPLOYMENT},
                "contract_months": {"type": "INTEGER"},
                "work_mode": {"type": "STRING", "enum": WORK},
                "salary": {"type": "STRING"},
            }}


def prompt(posting: str) -> str:
    kinds = ", ".join(f"{t['id']}={t['name']}" for t in jobtypes.taxonomy()["types"])
    return (
        "채용공고에서 아래 항목을 뽑는다. 공고에 적힌 것만 뽑고, 적혀 있지 않으면 빈 목록이나 '적혀 있지 않음'으로 둔다.\n"
        "- level: 직급. 제목·본문에 주니어/시니어/리드·매니저 표기나 연차로 드러날 때만\n"
        "- manages: 사람을 관리하는 팀장 자리인지(팀장), 관리 없이 기술을 이끄는지(테크 리드), 실무자인지\n"
        "- duties: 주요 업무 3~5개. 업무마다 text(30자 안쪽), kind(그 업무가 어느 직무의 일인지 아래 목록에서 하나), "
        "scope(책임 범위: 총괄·결정=전체를 맡아 방향을 정하고 이끔, 수행=맡아서 직접 해냄, 운영·유지=있는 것을 맡아 돌림, 보조=일부를 도움)\n"
        f"  kind 목록: {kinds}\n"
        "- required_skills / preferred_skills: 자격요건(필수)과 우대사항에 나온 기술·도구·방법론 이름. "
        "'Python', 'Spark', 'Airflow', '데이터 모델링'처럼 짧게, 문장 말고 이름만\n"
        "- years: 연수 요건. 예) '데이터 엔지니어링 3~7년' → area '데이터 엔지니어링', min 3, max 7(상한이 없으면 max를 비운다). "
        "총 경력만 있으면 area '총 경력'\n"
        "- company_domain: 이 공고로 사람을 뽑는 회사가 일하는 시장 1~2개. 회사 소개·서비스 설명으로 정한다. "
        "헤드헌팅 공고는 서치펌이 아니라 본문의 의뢰 회사 설명('국내 핀테크 유니콘' 등)으로 정하고, 그런 설명이 없으면 비운다"
        "(서치펌 자신의 업종은 적지 않는다)\n"
        "- domain_quotes: 지원자에게 특정 업종 경험·이해를 요구·우대하는 문장을 본문 그대로 한 문장씩. "
        "회사 소개·담당 업무 문장은 빼고, 없으면 빈 목록\n"
        "- degree, majors, major_need: 학력, 전공 이름, 전공이 필수인지 우대인지\n"
        "- certs: 자격증 이름\n"
        "- english: need(영어가 필수인지 우대인지)와 uses(영어를 쓰는 곳: 회의·협업, 문서·보고, 고객 응대, 공고가 영어. 적힌 것만)\n"
        "- employment: 고용 형태, contract_months: 계약직이면 계약 기간(개월, 모르면 비움)\n"
        "- work_mode: 근무 방식. salary: 연봉 표기 그대로(없으면 빈 문자열)\n\n"
        f"[공고]\n{posting}"
    )


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


# 문장이 놓인 본문 제목: 업무 아래면 버리고, 자격·필수면 필수, 우대면 우대(못 찾으면 우대)
# 본문 제목(줄 하나가 통째로 제목일 때만). 순서가 우선순위: 'Preferred Qualifications'는 우대
_HEADS = [("버림", r"복리후생|혜택|근무조건|근무환경|전형절차|채용절차|지원방법|제출서류|회사소개|기업소개|About|Benefits"),
          ("업무", r"주요업무|담당업무|업무내용|하는일|직무영역|이런일|Responsibilities|Whatyou'lldo"),
          ("우대", r"우대|Plus|Preferred|Nicetohave|더좋아요|있으면좋"),
          ("필수", r"자격(?:요건|조건|사항)|지원자격|필수|이런분|주요확인사항|Requirements|Qualifications")]
_ITEM = re.compile(r"^\s*(?:[-*•·ㆍ○✓✔]|\d+\)|\(\d+\))")  # 글머리표로 시작하는 줄은 항목이지 제목이 아님
_HEAD_CHARS = 30  # 공백을 뺀 글자 수가 이보다 긴 줄은 문장으로 본다


def _headings(text: str) -> list[tuple[int, str]]:
    """(squash한 본문에서의 위치, 제목 종류). 글머리표 없이 짧은 줄에서 제목 말을 찾는다."""
    out, pos = [], 0
    for line in (text or "").split("\n"):
        sq = _squash(line)
        if sq and len(sq) <= _HEAD_CHARS and not _ITEM.match(line):
            for kind, pat in _HEADS:
                if re.search(pat, sq, re.I):
                    out.append((pos, kind))
                    break
        pos += len(sq)
    return out


def _section(heads: list[tuple[int, str]], at: int) -> str | None:
    """at 앞에 마지막으로 나온 제목의 종류(없으면 None)."""
    kind = None
    for pos, k in heads:
        if pos > at:
            break
        kind = k
    return kind


# 경험을 묻는 말('근무'는 근무 형태 문장에 걸려서 경험·경력이 붙을 때만)
_EXP = re.compile(r"경험|이해|지식|출신|해\s*보신|해\s*본|수행|근무\s*(?:경험|경력|이력)|근무하신")
RULES_V = 4  # clean_domain·rule_quotes 규칙을 바꾸면 올린다(저장된 문장으로 AI 없이 다시 계산)


def rule_quotes(text: str) -> list[str]:
    """본문에서 코드로 찾는 업종 경험 문장 후보: 업종 사전 말과 경험·이해 같은 말이 함께 있는 줄(AI가 빠뜨린 문장을 채운다).
    자격요건·우대 제목 아래 줄만 clean_domain에서 남긴다."""
    out = []
    # 'ㆍ'는 앞뒤가 띄어져 있을 때만 글머리표(붙어 있으면 '물류ㆍ제조'처럼 문장 안 구분점)
    for line in re.split(r"\n|[•○◎▶■□]|\sㆍ\s|(?<=[.!?])\s+|(?:^|\s)[-*]\s|\d+[).]\s", text or ""):
        line = line.strip(" -*,ㆍ·")
        if 6 <= len(line) <= 200 and _EXP.search(line) and taxonomy.industries_in(line):
            out.append(line)
    return out


def _inline_need(q: str) -> str | None:
    """문장 자체에 붙은 표시: '(우대)', '… 우대', '[필수]' 같은 것만(문장 속 '필수는 아닙니다'는 아님)."""
    if re.search(r"^[\(\[]?우대[\)\]]|[\(\[]우대[\)\]]|우대$", q):
        return "우대"
    if re.search(r"^[\(\[]?필수[\)\]]|[\(\[]필수[\)\]]|필수$", q):
        return "필수"
    return None


def clean_domain(f: dict[str, Any], text: str) -> dict[str, Any]:
    """업종 경험(AI 다음, 호출 없음). 문장은 AI(domain_quotes)와 코드(rule_quotes)가 함께 찾고, 나머지는 코드가 정한다:
    본문에 없는 문장·관심만 묻는 문장·업무/복리후생/회사 소개 아래 문장은 버리고(코드가 찾은 문장은 자격요건·우대 아래만),
    업종 코드는 사전(industries.yaml words), 필수·우대는 문장 표시 → 문장이 놓인 제목(못 찾으면 우대).
    같은 코드는 필수만, 대분류가 같은 필수/우대로 있으면 그 아래 중분류는 뺀다. 사전에 걸리지 않은 문장은 domain_unmatched(월간 점검).
    다른 모듈이 읽는 domain_required·domain_preferred(코드)도 만든다. 회사 도메인은 앞 2개. 저장된 문장으로 다시 계산할 수 있다."""
    body = _squash(text)
    heads = _headings(text)
    keep: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    ai = list(dict.fromkeys(f.get("domain_quotes") or []))
    quotes = [(q, True) for q in ai] + [(q, False) for q in rule_quotes(text) if q not in ai]
    for quote, from_ai in quotes:
        q = _squash(quote).strip("\"'….")
        at = body.find(q)
        if len(q) < 4 or at < 0 or ("관심" in q and not re.search(r"경험|이해|지식", q)):
            continue
        sec = _section(heads, at)
        if sec in ("업무", "버림") or (not from_ai and sec not in ("필수", "우대")):
            continue
        codes = taxonomy.industries_in(quote)
        if not codes:
            unmatched.append(quote)
        need = _inline_need(q) or ("필수" if sec == "필수" else "우대")
        for c in codes:
            if c not in keep or need == "필수":
                keep[c] = {"code": c, "need": need, "quote": quote}
    # 대분류가 같은 필수/우대로 있으면 그 아래 중분류는 뺀다(금융 필수 + 보험 우대는 둘 다 남김)
    exp = [d for c, d in keep.items()
           if not (len(c) == 6 and c[:4] in keep and keep[c[:4]]["need"] == d["need"])]
    return {**f, "company_domain": (f.get("company_domain") or [])[:2], "domain_exp": exp,
            "domain_unmatched": unmatched,
            "domain_required": [d["code"] for d in exp if d["need"] == "필수"],
            "domain_preferred": [d["code"] for d in exp if d["need"] == "우대"]}


def duty_texts(f: dict[str, Any]) -> list[str]:
    """업무 글 목록. 공고 정리 v1(글만)과 v2(글·종류·범위)를 함께 읽는다."""
    return [d if isinstance(d, str) else d.get("text", "") for d in f.get("duties") or []]


def english_need(f: dict[str, Any]) -> str:
    e = f.get("english")
    return (e or {}).get("need", "적혀 있지 않음") if isinstance(e, dict) else (e or "적혀 있지 않음")


def load(data_dir: Path, file: str = FILE) -> dict[str, dict[str, Any]]:
    path = data_dir / file
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["uid"]] = r
    return out


def save(data_dir: Path, rows: dict[str, dict[str, Any]], file: str = FILE) -> None:
    lines = [json.dumps(rows[k], ensure_ascii=False, sort_keys=True) for k in sorted(rows)]
    (data_dir / file).parent.mkdir(parents=True, exist_ok=True)
    (data_dir / file).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def is_current(row: dict[str, Any] | None, has_body: bool = False) -> bool:
    """지금 지시문·업종 목록으로 정리했고, 본문이 생겼으면(본문 읽기) 본문까지 보고 정리했는지."""
    return (bool(row) and row.get("prompt") == PROMPT_VERSION
            and row.get("industries_v") == config.load("profile")["version"]
            and (row.get("body", True) or not has_body))


def posting_text(p: dict[str, Any], company: str, body: str | None) -> str:
    head = f"{company} | {p['title']} | {p.get('career', '')} | {', '.join(p.get('employment') or [])}"
    return head + "\n" + ((body or "")[:BODY_CHARS] or "(본문 없음)")


def run(data_dir: Path, screen: dict[str, Any], bodies: dict[str, Any], wanted: list[str],
        client: Any | None, today: str, max_calls: int | None = None, max_minutes: float | None = None,
        file: str = FILE, clients: list[Any] | None = None) -> dict[str, Any]:
    """wanted(후보 공고 id, 앞에서부터 먼저)에서 아직 정리하지 않은 것을 하루 한도까지 정리한다.
    file을 바꾸면(시험) 그 파일에만 쓴다. clients(키마다 하나)를 주면 함께 돌린다(따라잡기)."""
    rows = load(data_dir, file)
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    def has_body(pid: str) -> bool:
        return len(texts.get(pid) or "") >= bodyread.MIN_TEXT

    by_id = {p["id"]: p for p in screen["postings"]}
    summary: dict[str, Any] = {"wanted": len(wanted), "done": 0, "calls": 0}
    recomputed = 0
    # 업종 사전·규칙이 바뀌었으면 저장된 문장으로 업종 경험만 다시 계산(AI 호출 없음)
    wh = words_hash()
    for pid, row in rows.items():
        if row.get("prompt") == PROMPT_VERSION and row.get("words") != wh and pid in texts and pid in by_id:
            company = (screen["companies"].get(by_id[pid]["company"]) or {}).get("name", "")
            row["facts"] = clean_domain(row["facts"], posting_text(by_id[pid], company, texts.get(pid)))
            row["words"] = wh
            recomputed += 1
    if recomputed:
        summary["recomputed"] = recomputed
        save(data_dir, rows, file)
    todo = [pid for pid in wanted if pid in texts and not is_current(rows.get(pid), has_body(pid))]
    summary["pending"] = len(todo)
    if not todo:
        return summary
    if client is None:
        summary["skipped"] = "GEMINI_API_KEY 없음"
        return summary
    cfg = config.load("ai").get("facts") or {}
    limit = max_calls or cfg.get("max_calls", 250)
    deadline = time.monotonic() + (max_minutes or cfg.get("max_minutes", 20)) * 60
    errors: list[str] = []
    queue = list(todo)
    lock = threading.Lock()
    names = _domain_names()

    def work(c: Any) -> None:
        """클라이언트 하나(키 하나)로 줄에서 공고를 꺼내 정리한다. 여러 개가 함께 돈다(clients).
        Gemini 서버 오류(503)는 가끔 나서, 이 키로 5번 잇달아 실패할 때만 멈춘다(실패한 공고는 다음 실행에서)."""
        fails = 0
        while True:
            with lock:
                if not queue or summary["calls"] >= limit or time.monotonic() > deadline or fails >= 5:
                    return
                pid = queue.pop(0)
                summary["calls"] += 1
            p = by_id[pid]
            company = (screen["companies"].get(p["company"]) or {}).get("name", "")
            try:
                text = posting_text(p, company, texts.get(pid))
                raw = c.json(prompt(text), schema())
                raw["company_domain"] = [names[n] for n in raw.get("company_domain") or [] if n in names]
                got = clean_domain(raw, text)
            except Exception as e:  # 남은 건 다음 실행에서
                fails += 1
                with lock:
                    errors.append(str(e)[:200])
                continue
            fails = 0
            with lock:
                rows[pid] = {"uid": pid, "facts": got, "prompt": PROMPT_VERSION,
                             "industries_v": config.load("profile")["version"], "words": words_hash(),
                             "model": getattr(c, "model", None), "on": today, "body": has_body(pid)}
                summary["done"] += 1
                if summary["done"] % 25 == 0:
                    save(data_dir, rows, file)  # 중간에 멈춰도 한 일은 남긴다
                    log.info("공고 정리 %d/%d건", summary["done"], len(todo))

    workers = clients or [client]
    if len(workers) == 1:
        work(workers[0])
    else:
        threads = [threading.Thread(target=work, args=(c,)) for c in workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        summary["workers"] = len(workers)
    save(data_dir, rows, file)
    summary["pending"] = len(todo) - summary["done"]
    if errors:
        summary["errors"] = errors[:3]
        summary["error_count"] = len(errors)
    return summary


def candidates_for_all(screen: dict[str, Any], settings: list[dict[str, Any]]) -> list[str]:
    """사람마다 매칭 대상(내 분야 공고, recommend.match_scope)의 합집합. 누군가의 조건 필터까지 통과해 목록에 보이는
    공고 먼저(매칭 순서와 같게), 그 안에서 최근 공고부터."""
    defaults = config.load("filters")
    seen: dict[str, str] = {}
    shown: set[str] = set()
    for user_filters in [{**defaults, **(s.get("filters") or {})} for s in settings] or [defaults]:
        for p in recommend.candidates(screen, recommend.match_scope(user_filters)):
            seen[p["id"]] = p.get("firstSeen", "")
        shown |= {p["id"] for p in recommend.candidates(screen, user_filters)}
    return sorted(seen, key=lambda pid: (pid in shown, seen[pid], pid), reverse=True)


def _norm_skill(name: str) -> str | None:
    """공고에서 뽑은 스킬 이름을 사전 이름으로 맞춘다. 사전에 없으면 그대로(목록에 추가할 후보)."""
    n = re.sub(r"\s+", " ", name or "").strip(" -·,./()")
    if not n or len(n) > 30:
        return None
    found = matching.extract_skills(n)
    return next(iter(found)) if len(found) == 1 else n


def skill_catalog(texts: dict[str, str], rows: dict[str, dict[str, Any]], limit: int = 500) -> list[dict[str, Any]]:
    """프로필에서 고르는 스킬 목록: 공고 본문에서 사전으로 찾은 스킬 + 공고 정리에서 뽑은 스킬, 나온 공고 수 순."""
    counts: dict[str, int] = {}
    shown: dict[str, dict[str, int]] = {}
    for pid in set(texts) | set(rows):
        names = set(matching.extract_skills(texts[pid])) if pid in texts else set()
        f = (rows.get(pid) or {}).get("facts") or {}
        for raw in (f.get("required_skills") or []) + (f.get("preferred_skills") or []):
            n = _norm_skill(raw)
            if n:
                names.add(n)
        for n in {x.lower(): x for x in names}.values():
            key = n.lower()
            counts[key] = counts.get(key, 0) + 1
            shown.setdefault(key, {})
            shown[key][n] = shown[key].get(n, 0) + 1
    dictionary = {s.lower() for g in config.load("skills")["groups"].values() for s in (i["name"] for i in g)}
    # 표기가 여럿이면 많이 쓴 것, 같으면 대문자가 있는 것
    out = [{"name": max(shown[k], key=lambda x: (shown[k][x], x != x.lower(), x)), "count": c}
           for k, c in counts.items() if c >= 2 or k in dictionary]
    out.sort(key=lambda x: (-x["count"], x["name"]))
    return out[:limit]
