"""기업 구분(docs/collection.md '기업 구분과 그룹'): 공적 근거를 순서대로 찾아 처음 걸리는 근거로 정한다.

구분: 공공 · 대기업 · 외국계 · 중견 · 중소·스타트업 · 확인 안 됨. 표시: 상장.
근거 순서:
1. 공공기관 목록(재정경제부 공공기관 지정현황 · 행정안전부 지방공기업 · 지방출자출연기관) → 공공
2. 공정위 대규모기업집단 소속회사 → 대기업. DART 법인등록번호가 같으면(group_keys의 '#번호'), 번호가 없으면 회사 키
   또는 이어진 DART 법인 이름의 키가 같을 때
3. DART 감사보고서 지배기업이나 사업보고서 최대주주가 외국 회사 → 외국계(dart.foreign_owner).
   DART에서 읽었는데 외국이 아니면 수집처의 외국계 표시는 버린다. 읽지 못했을 때만 수집처 표시(근거에 '수집처 표시')
4. DART 실적: 3년 평균 매출이 중소기업기본법 업종별 기준을 넘으면 중견, 아니면 중소·스타트업
5. DART 실적이 없음: 국민연금 사업장 후보가 있고 모두 300명 미만이면 중소·스타트업(외부감사 대상이 아닌 작은 회사).
   직원 수는 화면에 보이지 않는다
6. 수집처가 대기업·공공으로 표시 → 그 구분(근거에 '수집처 표시')
7. 없음 → 확인 안 됨
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 중소기업기본법 시행령 별표1: 주된 업종별 평균매출액 기준(억 원). KSIC 중분류(두 자리) → 기준
_C_1500 = {14, 15, 17, 24, 28, 32}
_C_800 = {11, 18, 21, 23, 27, 33}
_C_600 = {34}


def sme_limit(industry_code: str | None) -> int:
    """업종 코드(KSIC, DART induty_code) → 중소기업 매출 기준(억 원). 모르면 가장 높은 1500."""
    try:
        d = int(str(industry_code)[:2])
    except (TypeError, ValueError):
        return 1500
    if 10 <= d <= 34:
        return 1500 if d in _C_1500 else 800 if d in _C_800 else 600 if d in _C_600 else 1000
    if d <= 8 or d == 35 or d == 36 or 41 <= d <= 47:
        return 1000  # 농림어업·광업·전기가스·수도·건설·도소매
    if 37 <= d <= 39 or 49 <= d <= 52 or 58 <= d <= 63:
        return 800   # 하수폐기물·운수창고·정보통신
    if 70 <= d <= 75 or 86 <= d <= 87 or 90 <= d <= 91 or 94 <= d <= 96:
        return 600   # 전문과학기술·사업지원·보건복지·예술스포츠·수리기타
    if 55 <= d <= 56 or 64 <= d <= 69 or d == 76 or d == 85:
        return 400   # 숙박음식·금융보험·부동산·임대·교육
    return 1500


def group_index(groups: dict[str, Any]) -> dict[str, str]:
    """공정위 목록 → {회사 키: 집단, '#법인등록번호': 집단}."""
    out: dict[str, str] = {}
    for c in groups.get("companies") or []:
        out[c["key"]] = c["group"]
        if c.get("jurirno"):
            out["#" + c["jurirno"].replace("-", "")] = c["group"]
    return out


SMALL_MAX = 300  # 국민연금 가입자 수가 이보다 적으면 작은 회사로 본다(화면에는 안 보임)


@dataclass
class Result:
    type: str
    basis: str
    listed: bool = False


def classify(key: str, *, corp: dict[str, Any] | None, basics: dict[str, Any] | None,
             group_keys: dict[str, str], public_keys: dict[str, str] | set[str], nps: dict[str, tuple[int, int]],
             source_type: str, manual: dict[str, Any] | None = None) -> Result:
    corp = corp or {}
    code = corp.get("corp_code")
    listed = bool(corp.get("stock_code"))
    if manual and manual.get("type"):
        # 예외(config/company_class.yaml): 사람이 근거를 확인해 정한 구분
        return Result(manual["type"], f"직접 확인: {manual.get('basis') or ''}".strip(), listed)
    dart_key = corp.get("dart_key")
    pk = key if key in public_keys else dart_key if dart_key and dart_key in public_keys else None
    if pk:
        label = public_keys.get(pk) if isinstance(public_keys, dict) else None
        return Result("공기업·공공기관", label or "공공기관 목록", listed)
    jurir = ((basics or {}).get("company") or {}).get("jurir_no")
    g = (group_keys.get(f"#{jurir}") if jurir else None) or group_keys.get(key) \
        or (group_keys.get(dart_key) if dart_key else None)
    if g:
        return Result("대기업", f"공정위 기업집단 {g}", listed)
    owner = (basics or {}).get("owner")
    if owner and owner.get("foreign"):
        return Result("외국계", f"DART {owner['source']} {owner['name'][:40]}", listed)
    # DART에서 지배기업·최대주주를 읽었는데 외국이 아니면 수집처의 외국계 표시는 믿지 않는다
    checked = basics is not None and "owner" in basics
    if source_type == "외국계" and not checked:
        return Result("외국계", "수집처 표시", listed)
    fin = (basics or {}).get("finance") or {}
    years = [y.get("revenue") for y in fin.get("years") or [] if y.get("revenue")]
    if code and years:
        avg = sum(years[-3:]) / len(years[-3:]) / 1e8
        limit = sme_limit(((basics or {}).get("company") or {}).get("industry_code"))
        if avg > limit:
            return Result("중견", f"DART 매출 {round(avg):,}억(기준 {limit:,}억)", listed)
        return Result("중소·스타트업", f"DART 매출 {round(avg):,}억(기준 {limit:,}억)", listed)
    cand = nps.get(key)
    if cand and cand[1] < SMALL_MAX:
        return Result("중소·스타트업", "DART 실적 공시 없음(작은 회사 확인)" if not code else "DART 실적 없음(작은 회사 확인)",
                      listed)
    if source_type in ("대기업", "공기업·공공기관"):
        return Result(source_type, "수집처 표시", listed)
    return Result("확인 안 됨", "근거 없음" if not cand else "직원 300명 이상인데 DART 실적 없음", listed)


# ---------- 회사 업종(docs/taxonomy.md '업종') ----------

def industry(*, manual: dict[str, Any] | None, public_label: str | None, ksic: str | None,
             domains: list[str]) -> tuple[str | None, str]:
    """회사 업종(중분류 코드 또는 None)과 근거. 순서: 예외 → 공공기관 목록 → KSIC 대응표 → 공고 정리의 회사 도메인
    다수결(헤드헌팅 공고는 넣지 않고 부른다) → 확인 안 됨. KSIC가 도메인을 알려 주지 않는 코드면 회사 도메인으로 간다."""
    from . import taxonomy

    if manual and manual.get("industry"):
        return manual["industry"], f"직접 확인: {manual.get('basis') or ''}".strip()
    if public_label:
        return "IN1101", public_label
    code, why = taxonomy.industry_from_ksic(ksic)
    if code:
        return code, f"DART 업종 코드 {ksic}"
    if domains:
        counts: dict[str, int] = {}
        for d in domains:
            counts[d] = counts.get(d, 0) + 1
        best = max(counts, key=lambda c: (counts[c], -domains.index(c)))
        total = len(domains)
        return best, f"공고 정리(AI) 회사 도메인 {total}개 중 {counts[best]}개"
    return None, "근거 없음" if why == "none" else f"DART 업종 코드 {ksic}(도메인 모름)"
