// 개인 필터. src/jobpost/filters.py와 같은 규칙이다(둘 중 하나를 고치면 다른 쪽도 고친다).
import type { Company, Filters, Posting } from './types'

export function passes(p: Posting, c: Company | undefined, f: Filters): boolean {
  const title = p.title
  const company = c?.name ?? p.company
  const squash = (s: string) => s.replaceAll(' ', '')
  for (const kw of f.exclude_keywords ?? []) {
    if (squash(title).includes(squash(kw))) return false
  }
  for (const x of f.exclude_companies ?? []) {
    if (x && company.includes(x)) return false
  }
  if ((f.always_companies ?? []).some((x) => x && company.includes(x))) return true

  const types = f.company_types
  if (types && types.length && !types.includes(c?.type ?? '그 외')) return false

  const fmin = f.career?.min ?? null
  const fmax = f.career?.max ?? null
  if (fmin !== null || fmax !== null) {
    const lo = p.careerMin || 0
    const hi = p.careerMax ?? 99
    if (fmin !== null && hi < fmin) return false
    if (fmax !== null && lo > fmax) return false
  }

  const regions = f.regions
  if (regions && regions.length && p.regions.length) {
    const remoteOk = regions.includes('원격') && ['재택', '원격', '리모트'].some((w) => title.includes(w))
    if (!remoteOk && !p.regions.some((r) => regions.some((a) => r.includes(a)))) return false
  }
  return true
}

export function matchesQuery(p: Posting, c: Company | undefined, q: string): boolean {
  const s = q.trim().toLowerCase()
  if (!s) return true
  return p.title.toLowerCase().includes(s) || (c?.name ?? p.company).toLowerCase().includes(s)
}
