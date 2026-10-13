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
  sources: SourceLink[]
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

export interface Screen {
  version: number
  date: string
  built: string
  counts: { open: number; new: number; companies: number }
  defaultFilters: Filters
  jobTypes: JobType[]
  companies: Record<string, Company>
  postings: Posting[]
}
