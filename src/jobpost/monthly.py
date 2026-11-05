"""월간 점검(기업 구분·업종 점검 보고, docs/taxonomy.md '정기 점검'): 고치지 않고 숫자와 목록만 낸다.

- 업종: 업종별 공고 분포와 확인 안 됨·기타 비율, 15%를 넘는 업종, 대응표에 없는 KSIC 코드,
  KSIC로 정한 업종과 공고 정리(AI) 회사 도메인이 다른 회사, 업종 사전에 걸리지 않은 업종 경험 문장
- 예외(config/company_class.yaml): 예외 없이 정한 값과 비교(같으면 지워도 됨, 다르면 둘 다)
공고·회사 이름은 공개 데이터라 그대로 쓴다(개인 프로필 정보는 없음).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import config, facts, recommend, screen, taxonomy
from .companies import CompanyRegistry

SHARE_SPLIT = 0.15  # 한 업종이 내 분야 공고의 이보다 많으면 갈라 볼지 묻는다


def report(data_dir: Path) -> list[str]:
    built, _ = screen.build(data_dir)
    registry = CompanyRegistry(data_dir / "companies.json")
    fx = facts.load(data_dir)
    mine = recommend.candidates(built, recommend.match_scope(config.load("filters")))
    out: list[str] = []
    name = taxonomy.industry_name

    # 1) 업종 분포
    by = Counter(p.get("industry") for p in mine)
    n = len(mine) or 1
    out.append(f"[업종] 내 분야 공고 {len(mine)}건")
    out.append(f"- 확인 안 됨 {by.get(None, 0)}건({by.get(None, 0) / n:.0%}), 기타 {by.get('IN9901', 0)}건")
    for code, k in by.most_common(12):
        if code:
            out.append(f"  {name(code)} {k}건({k / n:.0%})" + ("  ← 15% 넘음: 갈라 볼지" if k / n > SHARE_SPLIT else ""))

    # 2) KSIC: 대응표에 없는 코드, 대응표 업종 ≠ 회사 도메인 다수결
    ev = registry._evidence()
    corps, basics = ev.get("corps") or {}, ev.get("basics") or {}
    posts = Counter(p["company"] for p in mine)
    domains: dict[str, Counter[str]] = {}
    for p in mine:
        if not p.get("headhunter"):
            for d in ((fx.get(p["id"]) or {}).get("facts") or {}).get("company_domain") or []:
                domains.setdefault(p["company"], Counter())[d] += 1
    unmapped: Counter[str] = Counter()
    differ: list[str] = []
    for key, k in posts.items():
        ksic = ((basics.get((corps.get(key) or {}).get("corp_code") or "") or {}).get("company") or {}).get("industry_code")
        code, why = taxonomy.industry_from_ksic(ksic)
        if why == "unmapped":
            unmapped[str(ksic)] += k
        top = domains.get(key, Counter()).most_common(1)
        if code and top and top[0][0] != code:
            differ.append(f"  {built['companies'][key]['name']}: KSIC {ksic} → {name(code)} / 공고 정리 {name(top[0][0])} "
                          f"({top[0][1]}건), 공고 {k}건")
    out.append(f"- 대응표에 없는 KSIC 코드 {len(unmapped)}개" + (": " + ", ".join(f"{c}({k}건)" for c, k in unmapped.most_common(10))
                                                         if unmapped else ""))
    out.append(f"- KSIC 업종과 공고 정리 회사 도메인이 다른 회사 {len(differ)}곳")
    out += differ[:20]

    # 3) 업종 사전에 걸리지 않은 업종 경험 문장
    miss = Counter(q for p in mine for q in ((fx.get(p["id"]) or {}).get("facts") or {}).get("domain_unmatched") or [])
    out.append(f"- 업종 사전에 걸리지 않은 업종 경험 문장 {sum(miss.values())}개(같은 문장 묶음 {len(miss)}개)")
    out += [f"  {k}회 · {q[:80]}" for q, k in miss.most_common(20)]

    # 4) 예외: 예외 없이 정하면 무엇이 되는지
    out.append("[예외] config/company_class.yaml")
    for key, m in (config.load("company_class").get("overrides") or {}).items():
        auto = registry.classify(key, use_manual=False)
        line = f"- {key}: 예외 {m.get('type', '-')}"
        if auto:
            from_dart = auto.basis.startswith("DART")
            line += f" / 예외 없이 {auto.type}({auto.basis})"
            if auto.type == m.get("type"):
                line += " → 같음: 예외를 지워도 됨"
            elif from_dart:
                line += " → DART 값이 예외와 다름: 어느 쪽을 쓸지 묻기(답 전에는 예외)"
        if m.get("industry"):
            auto_ind, ind_basis = registry.industry(key, list(domains.get(key, Counter()).elements()), use_manual=False)
            line += f" / 업종 예외 {name(m['industry'])}, 예외 없이 {name(auto_ind) if auto_ind else '확인 안 됨'}({ind_basis})"
            if auto_ind == m["industry"]:
                line += " → 같음: 업종 예외를 지워도 됨"
        if m.get("checked"):
            line += f", 확인한 날 {m['checked']}"
        out.append(line)
    return out
