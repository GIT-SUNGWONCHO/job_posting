import { useMemo, useState } from 'react'
import { copy } from '../copy'
import { FilterSheet, type FilterSection } from '../components/FilterSheet'
import { CompanyRow } from '../components/CompanyRow'
import { Chip, DOWN_ICON, Empty, JobRow, SEARCH_ICON, SLIDERS_ICON } from '../components/ui'
import { matchesQuery } from '../lib/filter'
import { addDays } from '../lib/format'
import { href } from '../lib/route'
import type { Match } from '../lib/matches'
import type { Filters, Posting, Screen } from '../lib/types'

export const PAGE = 50
export type Sort = 'recommend' | 'latest' | 'deadline'
/** sample: 기준 샘플(평가할 공고)만 본다. 개인 필터와 상관없이. withOpen: 회사 목록에서 열린 공고가 있는 회사만 */
export interface JobsUi { query: string; sort: Sort; limit: number; sample: boolean; withOpen: boolean }

/** 회사 목록의 이번 주 새 공고: 오늘을 포함한 최근 며칠 */
const WEEK = 7

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
  const sample = useMemo(() => {
    const ids = new Set(screen.sample ?? [])
    return screen.postings.filter((p) => ids.has(p.id))
  }, [screen])
  const rated = sample.filter((p) => matches.get(p.id)?.mine).length
  const shown = useMemo(
    () => sortPostings((ui.sample ? sample : passed).filter((p) => matchesQuery(p, c[p.company], ui.query)), ui.sort, matches),
    [passed, sample, c, ui.query, ui.sort, ui.sample, matches],
  )
  // 회사 목록: 기업 구분 필터에 맞는 회사 전부(공고가 없는 주요 기업 포함). 열린 공고가 많은 순.
  // 검색은 회사 이름, 또는 필터 통과 공고 제목. 검색할 때는 "공고 있는 회사" 칩과 상관없이 공고 없는 회사도 찾는다.
  // 평가할 공고만 볼 때는 그 공고의 회사만
  const companies = useMemo(() => {
    if (seg !== 'companies') return []
    const passedBy = new Map<string, Posting[]>()
    for (const p of shown) passedBy.set(p.company, [...(passedBy.get(p.company) ?? []), p])
    const open = new Map<string, number>()
    const fresh = new Map<string, number>()
    const weekStart = addDays(screen.date, -(WEEK - 1))
    for (const p of screen.postings) {
      if (p.noise) continue
      open.set(p.company, (open.get(p.company) ?? 0) + 1)
      if (p.firstSeen >= weekStart) fresh.set(p.company, (fresh.get(p.company) ?? 0) + 1)
    }
    const types = filters.company_types ?? []
    const q = ui.query.trim().toLowerCase()
    const nameHit = (name: string) => !q || name.toLowerCase().includes(q)
    return Object.entries(c)
      .filter(([key, co]) => passedBy.has(key) || (!ui.sample
        && (types.length === 0 || types.includes(co.type))
        && !(filters.exclude_companies ?? []).some((x) => x && co.name.includes(x))
        && nameHit(co.name)))
      .map(([key, co]) => ({ key, co, passed: passedBy.get(key) ?? [], open: open.get(key) ?? 0, fresh: fresh.get(key) ?? 0 }))
      .filter((r) => !ui.withOpen || q !== '' || r.open > 0)
      .sort((a, b) => b.open - a.open || b.passed.length - a.passed.length || a.co.name.localeCompare(b.co.name, 'ko'))
  }, [seg, shown, screen.postings, screen.date, c, filters, ui.query, ui.sample, ui.withOpen])

  const total = seg === 'jobs' ? shown.length : companies.length
  const rest = Math.max(total - ui.limit, 0)

  return (
    <div className="page">
      <header className="list-top">
        <div className="title-tabs" role="tablist">
          {seg === 'jobs'
            ? <><h1 role="tab" aria-selected="true">{copy.jobs.segJobs}</h1><a role="tab" aria-selected="false" href={href.companies}>{copy.jobs.segCompanies}</a></>
            : <><a role="tab" aria-selected="false" href={href.jobs}>{copy.jobs.segJobs}</a><h1 role="tab" aria-selected="true">{copy.jobs.segCompanies}</h1></>}
        </div>
        <label className="search-box">
          {SEARCH_ICON}
          <input type="search" placeholder={seg === 'jobs' ? copy.jobs.searchPlaceholder : copy.jobs.searchCompany} aria-label={copy.jobs.search} value={ui.query}
            onChange={(e) => setUi({ ...ui, query: e.target.value, limit: PAGE })} />
        </label>
      </header>
      <div className="chips scroll filter-row">
        {!ui.sample && (
          <button type="button" className="chip icon" aria-label={copy.filter.all} onClick={() => setSheet('jobs')}>{SLIDERS_ICON}</button>
        )}
        {sample.length > 0 && (
          <Chip selected={ui.sample} onClick={() => setUi({ ...ui, sample: !ui.sample, sort: 'recommend', limit: PAGE })}>
            {copy.jobs.sampleChip(rated, sample.length)}
          </Chip>
        )}
        {!ui.sample && (
          <>
            <Chip selected={(filters.job_types ?? []).length > 0} onClick={() => setSheet('jobs')}>{jobChip(filters)}{DOWN_ICON}</Chip>
            <Chip selected={(filters.company_types ?? []).length > 0} onClick={() => setSheet('types')}>{typeChip(filters)}{DOWN_ICON}</Chip>
            {seg === 'jobs' && <Chip selected={filters.career?.min != null || filters.career?.max != null} onClick={() => setSheet('career')}>{careerChip(filters)}{DOWN_ICON}</Chip>}
            {seg === 'jobs' && <Chip selected={(filters.regions ?? []).length > 0} onClick={() => setSheet('regions')}>{regionChip(filters)}{DOWN_ICON}</Chip>}
            {seg === 'companies' && <Chip selected={ui.withOpen} onClick={() => setUi({ ...ui, withOpen: !ui.withOpen, limit: PAGE })}>{copy.jobs.withOpenChip}</Chip>}
          </>
        )}
      </div>
      {ui.sample && <p className="note list-note">{copy.jobs.sampleNote}</p>}
      <div className="list-head">
        <span>{copy.jobs.total(total)}</span>
        {seg === 'jobs' ? (
          <label className="sort">
            <select aria-label={copy.jobs.sortLabel} value={ui.sort} onChange={(e) => setUi({ ...ui, sort: e.target.value as Sort, limit: PAGE })}>
              {matches.size > 0 && <option value="recommend">{copy.jobs.sort.recommend}</option>}
              <option value="latest">{copy.jobs.sort.latest}</option>
              <option value="deadline">{copy.jobs.sort.deadline}</option>
            </select>
            {DOWN_ICON}
          </label>
        ) : <span className="sort">{copy.jobs.companySort}</span>}
      </div>

      <div className="rows list">
        {total === 0 && <Empty>{seg === 'jobs' ? copy.jobs.empty : copy.jobs.emptyCompanies}</Empty>}
        {seg === 'jobs' && shown.slice(0, ui.limit).map((p) => (
          <JobRow key={p.id} p={p} c={c[p.company]} today={today} active={p.id === activeId} match={matches.get(p.id)} />
        ))}
        {seg === 'companies' && companies.slice(0, ui.limit).map(({ key, co, open, fresh }) => (
          <CompanyRow key={key} companyKey={key} co={co} open={open} fresh={fresh} />
        ))}
      </div>
      {rest > 0 && (
        <div className="list-more">
          <button type="button" className="btn block more" onClick={() => setUi({ ...ui, limit: ui.limit + PAGE })}>
            {copy.jobs.more(Math.min(rest, PAGE))}
          </button>
        </div>
      )}

      {sheet && (
        <FilterSheet value={filters} defaults={defaults} jobTypes={screen.jobTypes ?? []} regions={regions} focus={sheet}
          onClose={() => setSheet(null)} onSave={(f) => { onFilters(f); setSheet(null) }} />
      )}
    </div>
  )
}
