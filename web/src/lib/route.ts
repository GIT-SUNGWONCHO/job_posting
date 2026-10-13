import { useSyncExternalStore } from 'react'

// 주소 뒤 #/... 로 화면을 고른다. 서버 설정 없이 새로고침·뒤로 가기가 된다.
export type Route =
  | { name: 'report' }
  | { name: 'jobs'; seg: 'jobs' | 'companies' }
  | { name: 'job'; id: string }
  | { name: 'company'; key: string }
  | { name: 'career' }
  | { name: 'apply' }
  | { name: 'admin' }

export function parse(hash: string): Route {
  const [, a = '', b = ''] = hash.replace(/^#/, '').split('/')
  const arg = decodeURIComponent(b)
  switch (a) {
    case 'jobs':
      return { name: 'jobs', seg: arg === 'companies' ? 'companies' : 'jobs' }
    case 'job':
      return arg ? { name: 'job', id: arg } : { name: 'jobs', seg: 'jobs' }
    case 'company':
      return arg ? { name: 'company', key: arg } : { name: 'jobs', seg: 'companies' }
    case 'career':
    case 'apply':
    case 'admin':
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
  apply: '#/apply',
  admin: '#/admin',
  job: (id: string) => `#/job/${encodeURIComponent(id)}`,
  company: (key: string) => `#/company/${encodeURIComponent(key)}`,
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
