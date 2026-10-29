"""수집처가 다른 같은 공고를 묶는다.

같은 공고로 보는 조건: 회사가 같고(법인 표기·별칭·"보험" 같은 꼬리말 차이는 무시),
제목이 거의 같고, 둘 다 마감일이 있으면 7일 안쪽으로 차이 날 것.
수집처 두 곳 사이에서는 일대일로만 짝짓는다. 제목이 똑같은 짝부터 정해서
"(Pre-training)"과 "(Post-training)"처럼 한 글자만 다른 공고가 섞이지 않게 한다.
같은 수집처 안의 서로 다른 공고는 묶지 않는다(팀만 다른 같은 제목 공고가 많다).
단, 직행이 다른 플랫폼에서 같은 공고를 두 번 가져온 경우(제목 같고 출처 플랫폼 다름)는 묶는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from .normalize import PUNCT, clean_company, company_key

_COMPANY_SUFFIXES = ("화재해상보험", "해상화재보험", "생명보험", "보험", "코리아", "korea")
_COMPANY_PREFIXES = ("한국", "korea")
_RECRUIT_WORDS = re.compile(
    r"채용|모집|공고|경력직|경력사원|경력|신입|정규직|계약직|인턴|담당자|"
    r"\d+\s*년\s*(이상|이하|↑)?|상시|수시|채용시|마감|급구"
)
# 사람이 아니라 수집처를 고르는 순서. 본문이 있는 리멤버를 대표로 쓴다.
# 원티드·잡코리아는 나중에 붙여서 맨 뒤에 둔다(앞에 두면 이미 있던 묶음의 대표가 바뀌어 매칭·관심 표시가 끊긴다)
SOURCE_PRIORITY = {"remember": 0, "zighang": 1, "saramin": 2, "wanted": 3, "jobkorea": 4}


@dataclass
class Item:
    uid: str
    source: str
    company: str
    title: str
    deadline: date | None = None
    via: str | None = None


def company_family(name: str) -> str:
    key = company_key(name)
    for s in _COMPANY_SUFFIXES:
        if key.endswith(s) and len(key) > len(s) + 1:
            key = key[: -len(s)]
            break
    for p in _COMPANY_PREFIXES:
        if key.startswith(p) and len(key) > len(p) + 1:
            key = key[len(p):]
            break
    return key


def title_key(title: str, company: str) -> str:
    s = title or ""
    cname = clean_company(company)

    def unwrap(m: re.Match) -> str:
        inner = m.group(1)
        rest = _RECRUIT_WORDS.sub("", inner.replace(cname, ""))
        return " " if not PUNCT.sub("", rest) else f" {inner} "

    s = re.sub(r"[\[\(【<]([^\]\)】>]*)[\]\)】>]", unwrap, s)
    if cname:
        s = s.replace(cname, " ")
    s = _RECRUIT_WORDS.sub(" ", s)
    return PUNCT.sub("", s).lower()


def title_score(a: str, b: str) -> float:
    """제목 키 유사도. 0이면 다른 공고."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 6 and short in long_:
        return 0.95  # 수집처가 제목을 잘라 보여주는 경우
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= 0.85 else 0.0


def cluster(items: list[Item]) -> dict[str, str]:
    """uid → 대표 uid. 묶이지 않은 공고는 자기 자신을 가리킨다."""
    parent = {it.uid: it.uid for it in items}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    buckets: dict[str, list[tuple[Item, str]]] = {}
    for it in items:
        buckets.setdefault(company_family(it.company), []).append((it, title_key(it.title, it.company)))

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for group in buckets.values():
        candidates: list[tuple[float, int, int]] = []
        for i in range(len(group)):
            a, ta = group[i]
            for j in range(i + 1, len(group)):
                b, tb = group[j]
                if a.deadline and b.deadline and abs((a.deadline - b.deadline).days) > 7:
                    continue
                if a.source == b.source:
                    if a.source == "zighang" and ta and ta == tb and a.via != b.via:
                        union(a.uid, b.uid)
                    continue
                score = title_score(ta, tb)
                if score:
                    candidates.append((score, i, j))
        used: set[tuple[int, str]] = set()
        for _, i, j in sorted(candidates, key=lambda c: -c[0]):
            a, b = group[i][0], group[j][0]
            if (i, b.source) in used or (j, a.source) in used:
                continue
            used.add((i, b.source))
            used.add((j, a.source))
            union(a.uid, b.uid)

    members: dict[str, list[Item]] = {}
    for it in items:
        members.setdefault(find(it.uid), []).append(it)
    rep_of: dict[str, str] = {}
    for group in members.values():
        rep = min(group, key=lambda it: (SOURCE_PRIORITY.get(it.source, 9), it.uid))
        for it in group:
            rep_of[it.uid] = rep.uid
    return rep_of
