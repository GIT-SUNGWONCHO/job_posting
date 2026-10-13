# 채용공고 수집·매칭 앱

데이터·AI 경력 공고를 매일 모아 정리하고, 회사를 조사하고, 내 경력과 매칭해 웹 대시보드와 아침 카톡으로 보고하는 앱이다. 공고(시장 수요)로 내 커리어 방향을 점검하는 것도 큰 축이다. 처음 사용자는 데이터 엔지니어 경력 약 10년이고, 지인도 다른 직무로 쓸 수 있게 만든다.

이 파일은 안내판이다. 기준과 이유는 아래 문서에 있고, 같은 내용을 여기에 베끼지 않는다.

## 문서 지도

| 무엇 | 위치 |
| --- | --- |
| 기획: 무엇을 왜, 화면, 개발 순서, 정할 것 | [기획 문서](https://claude.ai/code/artifact/40724550-e947-4373-bc46-8367bbc709d2) |
| 화면 구성(확정 와이어프레임), 디자인 스타일 | [디자인 캔버스](https://claude.ai/artifact/5BJc5LRNaJCNgQRVuZ3PcE) |
| 구성도, 데이터 흐름, 저장 위치, 분류 기준 | `docs/architecture.md` |
| 수집 기준: 범위, 중복, 기업 구분, 수집처에서 확인된 사실 | `docs/collection.md` |
| 내용·형식·화면 원칙, 회사 리서치 모듈 | `docs/content-rules.md` |
| 용어와 표기 | `docs/glossary.md` |
| 결정 기록(날짜 · 결정 · 이유 · 다시 볼 조건) | `docs/decisions.md` |
| 대시보드 | https://careermap-web.oroloov.workers.dev (초대한 사람만 로그인) |
| 운영 설정: Supabase, Cloudflare, 키 넣는 곳 | `docs/setup.md` |
| 개발 흐름(다른 프로젝트에도 쓰는 진행 방식) | `docs/dev-workflow.md` |
| 실제 값: 수집 범위, 개인 필터, 직무 유형, AI 모델, 그룹 규칙, 회사 별칭 | `config/*.yaml` |
| 수집 데이터 | `data` 브랜치(형식은 그 브랜치 README) |

## 지금 단계

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| 0 | 기획, 수집처 검증, 화면 구성, 화면·콘텐츠 원칙 | 완료 |
| 1 | 개발 기반: 이 파일, 용어집, 데이터 형식 | 완료(기준 샘플은 3단계에서) |
| 2 | 수집, 아키텍처, 디자인 스타일, 대시보드 | 진행 중: 수집(매일 04:17 자동), 아키텍처·디자인 스타일 확정, 대시보드 첫 버전 배포. 남은 것: 실제로 써 보며 다듬기 |
| 3 | 매칭: 프로필·이력서, 직무 분류, 점수 | 진행 중: 직무 유형 분류(3-1)·필터 계정 저장(3-2)·프로필 입력(3-3) 완료, 매칭 점수(3-4) 다음 |
| 4 | 분석: 회사 리서치, 커리어 탭 | |
| 5 | 보고: 오늘의 리포트, 아침 카톡 | |
| 6 | 확장: 지원 상태, 지인 계정, 나머지 수집처 | |

## 꼭 지킬 것

- **지금은 내 것만 만든다.** 사용자는 본인 한 명 기준으로 정한다. 지인·공개 서비스를 위한 결정은 바로 정하지 않고 기획 문서 "정할 것"(6단계)에 적고 넘어간다. 지인을 받을 수 있는 구조(로그인, 사람별 데이터 분리, 공용 수집)는 깨지 않는다.
- **사실과 의견을 나눈다.** 회사 리서치는 사실만, AI 문장에는 출처 URL, 해석에는 "AI 의견". 자세한 건 `docs/content-rules.md`.
- **키와 개인정보:** 키·토큰은 GitHub Secrets와 환경 변수로만 쓰고 코드, 커밋, 로그에 남기지 않는다. 이력서와 프로필은 레포에 올리지 않는다(Supabase).
- **문구는 용어집을 따른다.** 새 용어는 `docs/glossary.md`에 먼저 추가한다. 화면 문구는 `web/src/copy.ts`, 색·크기 값은 `web/src/styles/tokens.css` 한 곳에만 둔다.
- **한 사실은 한 곳에.** 값은 `config/`, 기준과 이유는 `docs/`. 결정을 내리거나 바꾸면 같은 작업 안에서 `docs/decisions.md`와 해당 문서를 고친다.
- **수집처는 조심해서 다룬다.** 요청 간격과 시간 한도를 지키고, 일부만 받은 날에는 그 수집처 공고를 내려간 공고로 처리하지 않는다. 사이트에서 새로 확인한 사실은 날짜와 함께 `docs/collection.md`에 적는다.
- **실제 데이터로 정할 것은 미룬다.** 분량, 문장 길이, 계산법은 기획 문서의 "개발하며 정할 것"에 둔다.
- **보고 방식:** 사용자와는 한국어로, 결론부터 짧게. 결정이 필요하면 선택지 2~4개와 추천을 함께 낸다.

## 코드와 실행

수집·분석은 Python 3.12(uv), 화면은 React + Vite + TypeScript(`web/`, npm).

```
src/jobpost/
  models.py        공통 공고 형식(Posting, Detail)
  sources/         수집처별 수집기. 그 사이트에서 확인한 동작은 파일 맨 위에 적는다
  normalize.py     회사 이름, 경력·마감 표기(용어집 형식)
  scope.py         저장 범위(데이터·AI), 해외, 잡음 판단
  companies.py     기업 구분, 그룹 이름
  dedup.py         수집처가 다른 같은 공고 묶기
  filters.py       개인 필터(보는 목록에서만 거름)
  store.py         data 폴더 형식
  pipeline.py      하루 수집 한 번의 순서
  jobtypes.py      직무 유형 분류(목록은 config/job_types.yaml, AI가 고름)
  ai.py            AI 호출(Gemini). 외부 AI는 여기서만 부른다
  screen.py        화면용 파일 만들기(형식은 web/src/lib/types.ts와 같게)
  publish.py       화면용 파일을 Supabase 저장소에 올리기
config/            yaml 설정
supabase/migrations/  Supabase 표와 권한(SQL Editor에서 순서대로 실행)
tests/             파서·규칙 테스트, fixtures/에 실제 응답 일부
web/src/
  copy.ts          화면 문구(용어집 기준)
  styles/          tokens.css(디자인 값), app.css
  lib/             화면용 파일 형식·불러오기, 표기, 개인 필터(filters.py와 같은 규칙), 주소
  screens/         리포트, 공고·회사 목록, 공고 상세, 회사, 관리, 프로필
```

- 수집: `uv run jobpost collect --data-dir data` (시험은 `--max-pages 2 --detail-budget 5`)
- 검사: `uv run ruff check src tests` 와 `uv run pytest -q`, 화면은 `cd web && npm test && npm run lint && npm run build`
- 화면 개발: `uv run jobpost screen --data-dir <data> --out .dev-data/screen.json.gz` 후 `cd web && npm run dev`(Supabase 값이 없으면 로그인 없이 이 파일을 읽는다)
- 매일 실행: `.github/workflows/collect.yml`(04:17 KST). 결과는 `data` 브랜치에 커밋되고, 화면용 파일은 Supabase 저장소에 올라간다. 실행 요약은 Actions 화면과 `data` 브랜치 `runs/`에 남는다.
