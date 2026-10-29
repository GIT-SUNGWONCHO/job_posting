// 화면용 파일 형식. 만드는 쪽은 src/jobpost/screen.py
export type DeadlineType = 'date' | 'always' | 'until_filled'
export type CompanyType = '대기업' | '공기업·공공기관' | '외국계' | '그 외'

export interface SourceLink {
  source: string
  name: string
  url: string | null
}

export interface Posting {
  id: string
  company: string
  /** 원문 제목(공고 상세) */
  title: string
  /** 목록 제목: 회사 이름·'채용' 같은 말을 뺀 제목. 원문과 같으면 없다(listTitle()로 읽는다) */
  listTitle?: string
  careerMin: number | null
  careerMax: number | null
  career: string
  deadlineType: DeadlineType
  deadline: string | null
  regions: string[]
  employment: string[]
  headhunter: boolean
  /** 헤드헌팅 공고의 의뢰 회사 구분(수집처가 적어 준 것). 회사 자리는 서치펌이라 필터는 이걸 쓴다 */
  clientType?: CompanyType
  noise: string | null
  firstSeen: string
  /** 새로 붙인 수집처가 첫날 가져온 공고(원래 열려 있던 공고). 새 공고로 세지 않는다 */
  backfill?: boolean
  /** 직무 유형 id. 오늘 들어와 아직 분류 전이면 null */
  jobType: string | null
  /** 본문 파일(bodies/xx.json.gz)에 본문이 있나 */
  hasBody: boolean
  sources: SourceLink[]
}

export interface Body {
  text: string
  /** 본문을 가져온 수집처: remember·wanted·saramin(원문), zighang(직행이 정리한 요약) */
  source: string
}

export interface JobType {
  id: string
  name: string
  /** 좁은 곳(포지션 맵)에 쓰는 짧은 이름 */
  short?: string
  /** false: 커리어 방향으로 보지 않는 유형(커리어 탭에서 뺀다) */
  direction?: boolean
}

export interface Company {
  name: string
  type: CompanyType
  group: string | null
}

export interface Filters {
  job_types?: string[]
  exclude_keywords?: string[]
  always_companies?: string[]
  exclude_companies?: string[]
  company_types?: CompanyType[]
  career?: { min?: number | null; max?: number | null }
  regions?: string[]
}

/** 프로필에서 고르는 목록(config/profile.yaml) */
export interface ProfileOptions {
  version: number
  industries: { id: string; name: string }[]
  /** job_type: 공고에서는 이 직무 유형으로 본다(없으면 id가 같은 직무 유형) */
  roles: { id: string; name: string; job_type?: string }[]
  skill_levels: { level: number; name: string; desc: string }[]
  project_parts: string[]
  degrees: string[]
  major_groups: string[]
  english: string[]
}

/** 공고에서 나온 스킬과 나온 공고 수. 프로필 스킬은 이 안에서 고른다 */
export interface SkillOption {
  name: string
  count: number
}

export interface Screen {
  version: number
  date: string
  built: string
  counts: { open: number; new: number; companies: number }
  defaultFilters: Filters
  jobTypes: JobType[]
  profileOptions?: ProfileOptions
  skills?: SkillOption[]
  /** 기준 샘플 공고 id(config/match_sample.yaml). "평가할 공고" */
  sample?: string[]
  /** 커리어 탭 시장 지표(src/jobpost/career.py). 예전 파일에는 없다 */
  career?: CareerMetrics | null
  /** 마지막 수집 요약(관리 화면 수집 현황, v6부터). 아직 없으면 null */
  collection?: Collection | null
  /** 아침 알림 기본값과 고를 수 있는 값(config/notify.yaml, v6부터) */
  notify?: NotifyDefaults
  /** 판정마다 배점에 곱하는 비율(config/match_guide.yaml fit, v8부터). 판단 근거의 받은 점수 */
  matchFit?: Record<string, number>
  companies: Record<string, Company>
  postings: Posting[]
}

/** 마지막 수집: 언제 끝났고 수집처마다 끝까지 받았는지(일부만 받은 날은 그 수집처 공고를 내리지 않는다) */
export interface Collection {
  date: string
  /** 끝난 시각(한국 시간, 2026-10-26T06:58:08) */
  finished: string | null
  sources: { id: string; name: string; complete: boolean }[]
}

/** 아침 알림 기본값(config/notify.yaml). 화면 코드와 화면용 파일은 따로 배포되니 칸이 없어도 깨지지 않게 읽는다 */
export interface NotifyDefaults {
  channels?: string[]
  /** 마감 임박에 넣는 필터 통과 공고의 최소 점수 */
  soonMinScore?: number
  /** 마감 임박: 마감까지 남은 날 */
  soonDays?: number
}

/** 연차 구간: 최소 경력 0~3년 미만, 3~7, 7~12, 12년 이상, 연차 무관 */
export type CareerBucket = '0-3' | '3-7' | '7-12' | '12+' | 'any'

/** 커리어 지표. 묶음 이름은 "직무 유형 id|기업 구분"(분류 전은 none) */
export interface CareerMetrics {
  version: number
  /** 수집을 시작한 날 */
  since: string
  days: string[]
  /** 날짜별 열린 공고 수와 새 공고 수(수집 첫날의 새 공고는 null) */
  series: Record<string, { open: number[]; new: (number | null)[] }>
  /** 지금 열린 공고의 연차 분포, 요구 스킬(공고 수 많은 순), 본문이 있는 공고 수 */
  current: Record<string, { career: Partial<Record<CareerBucket, number>>; skills: [string, number][]; withBody: number }>
  /** 스킬 사전에 있는 이름(v2부터). 이 밖의 프로필 스킬은 공고에서 셀 수 없다 */
  dictionary?: string[]
}

/** 회사 기본정보 파일(companies.json.gz). 만드는 쪽은 src/jobpost/screen.py build_companies */
export interface CompaniesFile {
  version: number
  date: string
  /** 수집을 시작한 날(지난 공고는 이날부터) */
  since: string
  companies: Record<string, CompanyBasics>
}

export interface CompanyBasics {
  dart?: DartBasics | DartPending | DartNone
  /** 이 앱이 수집한 마감된 공고(최근 마감 순, 일부) */
  past?: PastPosting[]
  /** 마감된 공고 전체의 직무 유형별 수(분류 전은 none) */
  pastByJob?: Record<string, number>
  /** 심층분석 중 가진 데이터로 만드는 모듈(src/jobpost/research.py) */
  research?: { competitors?: Competitors; tools?: ToolsFound }
}

/** 경쟁사: DART 업종 코드가 같은 회사 중 매출이 큰 곳. rows 맨 앞은 이 회사(self) */
export interface Competitors {
  industry: string
  rows: {
    name: string; key: string | null; self: boolean; year: number | null; revenue: number | null; margin: number | null
    /** 연결 · 별도, 매출 자리 계정(매출액 · 영업수익), 사업보고서 접수번호. 예전 파일에는 없다 */
    basis?: string | null; revenueName?: string | null; rceptNo?: string | null
  }[]
}

/** 직무 환경·도구: 이 회사 공고 본문(postings건)에서 찾은 도구, 칸마다 공고 수 */
export interface ToolsFound {
  postings: number
  slots: { name: string; items: { skill: string; count: number }[] }[]
}

export interface PastPosting {
  id: string
  title: string
  listTitle?: string
  jobType: string | null
  firstSeen: string
  closedOn: string
}

/** DART와 이었고 기본정보를 받은 회사 */
export interface DartBasics {
  corpCode: string
  corpName: string
  /** 기업개황의 법인명(현대자동차(주)). 잘못 이은 회사를 알아볼 수 있게 보여준다 */
  legalName?: string | null
  /** 유가증권 · 코스닥 · 코넥스 · 기타 */
  market: string | null
  ceo: string | null
  founded: string | null
  homepage: string | null
  /** 사업보고서 주요 계정(원). 오래된 해부터 */
  finance: {
    year: number
    basis: '연결' | '별도'
    rceptNo: string | null
    /** 매출 자리에 쓴 계정: 매출액, 또는 영업수익(증권사·일부 플랫폼) */
    revenueName?: string
    years: { year: number; revenue?: number | null; operating?: number | null; net?: number | null }[]
  } | null
  /** 사업보고서 직원 현황. salary는 1인 평균(원), tenure는 평균 근속(년) */
  employees: { count: number; tenure: number | null; salary: number | null; rceptNo: string | null } | null
  disclosures: { date: string; title: string; rceptNo: string | null }[]
  fetched: string
}

/** 이었지만 기본정보는 아직 받기 전 */
export interface DartPending {
  corpCode: string
  corpName: string
  pending: true
}

/** DART에서 찾지 못함: none(같은 이름 없음), ambiguous·mixed(같은 이름 여럿), weak(믿기 어려운 이름이라 상장사만 봤는데 없음) */
export interface DartNone {
  none: string
  checked: string
}
