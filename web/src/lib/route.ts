import { useSyncExternalStore } from 'react'

// 주소 뒤 #/... 로 화면을 고른다. 서버 설정 없이 새로고침·뒤로 가기가 된다.
export type CareerSeg = 'market' | 'position' | 'plan'
const CAREER_SEGS: CareerSeg[] = ['market', 'position', 'plan']

export type Route =
  | { name: 'report' }
  | { name: 'jobs'; seg: 'jobs' | 'companies' }
  | { name: 'job'; id: string }
  | { name: 'company'; key: string }
  | { name: 'note'; key: string; section: number }
  | { name: 'career'; seg: CareerSeg }
  | { name: 'interest'; seg: 'jobs' | 'companies' }
  | { name: 'admin' }
  | { name: 'profile' }
  | { name: 'notify' }
  | { name: 'collection' }

export function parse(hash: string): Route {
  const [, a = '', b = '', c = ''] = hash.replace(/^#/, '').split('/')
  const arg = decodeURIComponent(b)
  switch (a) {
    case 'jobs':
      return { name: 'jobs', seg: arg === 'companies' ? 'companies' : 'jobs' }
    case 'job':
      return arg ? { name: 'job', id: arg } : { name: 'jobs', seg: 'jobs' }
    case 'company':
      return arg ? { name: 'company', key: arg } : { name: 'jobs', seg: 'companies' }
    case 'note': {
      const section = Number.parseInt(decodeURIComponent(c), 10)
      return arg ? { name: 'note', key: arg, section: Number.isFinite(section) ? section : -1 } : { name: 'jobs', seg: 'companies' }
    }
    case 'career':
      return { name: 'career', seg: CAREER_SEGS.includes(arg as CareerSeg) ? (arg as CareerSeg) : 'market' }
    case 'interest':
    case 'apply': // 예전 주소(지원 현황)
      return { name: 'interest', seg: arg === 'companies' ? 'companies' : 'jobs' }
    case 'admin':
    case 'profile':
    case 'notify':
    case 'collection':
      return { name: a }
    default:
      return { name: 'report' }
  }
}

export const href = {
  report: '#/report',
  jobs: '#/jobs',
  companies: '#/jobs/companies',
  career: '#/career',
  careerSeg: (seg: CareerSeg) => (seg === 'market' ? '#/career' : `#/career/${seg}`),
  interest: '#/interest',
  interestCompanies: '#/interest/companies',
  admin: '#/admin',
  profile: '#/profile',
  notify: '#/notify',
  collection: '#/collection',
  job: (id: string) => `#/job/${encodeURIComponent(id)}`,
  company: (key: string) => `#/company/${encodeURIComponent(key)}`,
  /** 내 리서치 노트. section을 주면 그 섹션으로 */
  note: (key: string, section?: number) => `#/note/${encodeURIComponent(key)}${section === undefined ? '' : `/${section}`}`,
}

function subscribe(cb: () => void) {
  window.addEventListener('hashchange', cb)
  return () => window.removeEventListener('hashchange', cb)
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  return parse(hash)
}

/** 앱 안에서 들어온 상세면 뒤로 가기, 주소로 바로 들어왔으면 목록으로. */
export function goBack(fallback: string) {
  if (window.history.length > 1) window.history.back()
  else window.location.hash = fallback
}
