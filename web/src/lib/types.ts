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
  title: string
  careerMin: number | null
  careerMax: number | null
  career: string
  deadlineType: DeadlineType
  deadline: string | null
  regions: string[]
  employment: string[]
  headhunter: boolean
  noise: string | null
  firstSeen: string
  /** 직무 유형 id. 오늘 들어와 아직 분류 전이면 null */
  jobType: string | null
  /** 본문 파일(bodies/xx.json.gz)에 본문이 있나 */
  hasBody: boolean
  sources: SourceLink[]
}

export interface Body {
  text: string
  /** 본문을 가져온 수집처: remember(원문), zighang(직행이 정리한 요약), saramin(원문) */
  source: string
}

export interface JobType {
  id: string
  name: string
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
  roles: { id: string; name: string }[]
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
  companies: Record<string, Company>
  postings: Posting[]
}
