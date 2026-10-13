import { useMemo, useState } from 'react'
import { copy } from '../copy'
import { FilterSheet, type FilterSection } from '../components/FilterSheet'
import { Chip, Empty, JobRow } from '../components/ui'
import { matchesQuery } from '../lib/filter'
import { href } from '../lib/route'
import type { Match } from '../lib/matches'
import type { Filters, Posting, Screen } from '../lib/types'

export const PAGE = 50
export type Sort = 'recommend' | 'latest' | 'deadline'
export interface JobsUi { query: string; sort: Sort; limit: number }

function jobChip(f: Filters): string {
  const n = (f.job_types ?? []).length
  return n === 0 ? copy.filter.allJobs : copy.filter.jobCount(n)
}
function typeChip(f: Filters): string {
  const t = f.company_types ?? []
  return t.length === 0 ? copy.filter.allTypes : copy.filter.more(t[0], t.length - 1)
}
function careerChip(f: Filters): string {
  const lo = f.career?.min ?? null
  const hi = f.career?.max ?? null
  if (lo === null && hi === null) return copy.filter.anyCareer
  if (lo !== null && hi !== null) return copy.filter.careerRange(lo, hi)
  return lo !== null ? copy.filter.careerMin(lo) : copy.filter.careerMax(hi as number)
}
function regionChip(f: Filters): string {
  const r = f.regions ?? []
  return r.length === 0 ? copy.filter.allRegions : copy.filter.more(r.slice(0, 2).join('·'), r.length - 2 > 0 ? r.length - 2 : 0)
}

function sortPostings(list: Posting[], sort: Sort, matches: Map<string, Match>): Posting[] {
  if (sort === 'recommend') {
    const score = (p: Posting) => matches.get(p.id)?.score ?? -1
    return [...list].sort((a, b) => score(b) - score(a))
  }
  if (sort === 'latest') return list // 화면용 파일이 이미 최신순
  const key = (p: Posting) => (p.deadlineType === 'date' && p.deadline ? p.deadline : '9999')
  return [...list].sort((a, b) => key(a).localeCompare(key(b)))
}

export function Jobs({ screen, passed, filters, defaults, regions, seg, ui, setUi, onFilters, today, activeId, matches }: {
  screen: Screen
  passed: Posting[]
  filters: Filters
  defaults: Filters
  regions: string[]
  seg: 'jobs' | 'companies'
  ui: JobsUi
  setUi: (u: JobsUi) => void
  onFilters: (f: Filters) => void
  today: string
  activeId?: string
  matches: Map<string, Match>
}) {
  const [sheet, setSheet] = useState<FilterSection | null>(null)
  const c = screen.companies
  const shown = useMemo(
    () => sortPostings(passed.filter((p) => matchesQuery(p, c[p.company], ui.query)), ui.sort, matches),
    [passed, c, ui.query, ui.sort, matches],
  )
  const companies = useMemo(() => {
    const by = new Map<string, Posting[]>()
    for (const p of shown) by.set(p.company, [...(by.get(p.company) ?? []), p])
    return [...by.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
  }, [shown])

  const total = seg === 'jobs' ? shown.length : companies.length
  const rest = Math.max(total - ui.limit, 0)

  return (
    <div className="page">
      <header className="page-head">
        <h1>{copy.jobs.title}</h1>
        <div className="seg" role="tablist">
          <a role="tab" aria-selected={seg === 'jobs'} className={seg === 'jobs' ? 'on' : ''} href={href.jobs}>{copy.jobs.segJobs}</a>
          <a role="tab" aria-selected={seg === 'companies'} className={seg === 'companies' ? 'on' : ''} href={href.companies}>{copy.jobs.segCompanies}</a>
        </div>
        <input className="search" type="search" placeholder={copy.jobs.searchPlaceholder} aria-label="검색" value={ui.query}
          onChange={(e) => setUi({ ...ui, query: e.target.value, limit: PAGE })} />
        <div className="chips scroll">
          <Chip selected={(filters.job_types ?? []).length > 0} onClick={() => setSheet('jobs')}>{jobChip(filters)} ▾</Chip>
          <Chip selected={(filters.company_types ?? []).length > 0} onClick={() => setSheet('types')}>{typeChip(filters)} ▾</Chip>
          <Chip selected={filters.career?.min != null || filters.career?.max != null} onClick={() => setSheet('career')}>{careerChip(filters)} ▾</Chip>
          <Chip selected={(filters.regions ?? []).length > 0} onClick={() => setSheet('regions')}>{regionChip(filters)} ▾</Chip>
        </div>
        <div className="list-head">
          <span>{seg === 'jobs' ? copy.jobs.count(shown.length) : copy.jobs.companyCount(companies.length)}</span>
          {seg === 'jobs' && (
            <select aria-label="정렬" value={ui.sort} onChange={(e) => setUi({ ...ui, sort: e.target.value as Sort, limit: PAGE })}>
              {matches.size > 0 && <option value="recommend">{copy.jobs.sort.recommend}</option>}
              <option value="latest">{copy.jobs.sort.latest}</option>
              <option value="deadline">{copy.jobs.sort.deadline}</option>
            </select>
          )}
        </div>
      </header>

      <div className="rows list">
        {total === 0 && <Empty>{copy.jobs.empty}</Empty>}
        {seg === 'jobs' && shown.slice(0, ui.limit).map((p) => (
          <JobRow key={p.id} p={p} c={c[p.company]} today={today} active={p.id === activeId} match={matches.get(p.id)} />
        ))}
        {seg === 'companies' && companies.slice(0, ui.limit).map(([key, list]) => (
          <a key={key} className="row" href={href.company(key)}>
            <span className="row-main">
              <span className="row-title">{c[key]?.name ?? key}</span>
              <span className="row-company">{[c[key]?.group && `${c[key]?.group} 계열`, c[key]?.type].filter(Boolean).join(' · ')}</span>
              <span className="row-meta"><span>{copy.jobs.openCount(list.length)}</span><span className="row-top">{list[0].title}</span></span>
            </span>
          </a>
        ))}
      </div>
      {rest > 0 && (
        <button type="button" className="more-btn" onClick={() => setUi({ ...ui, limit: ui.limit + PAGE })}>
          {copy.jobs.more(Math.min(rest, PAGE))}
        </button>
      )}

      {sheet && (
        <FilterSheet value={filters} defaults={defaults} jobTypes={screen.jobTypes ?? []} regions={regions} focus={sheet}
          onClose={() => setSheet(null)} onSave={(f) => { onFilters(f); setSheet(null) }} />
      )}
    </div>
  )
}
