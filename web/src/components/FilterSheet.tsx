import { useEffect, useState } from 'react'
import { copy } from '../copy'
import type { CompanyType, Filters, JobType } from '../lib/types'

const TYPES: CompanyType[] = ['대기업', '공기업·공공기관', '외국계', '그 외']

export type FilterSection = 'jobs' | 'types' | 'career' | 'regions'

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
}

function num(v: string): number | null {
  const n = Number.parseInt(v, 10)
  return Number.isFinite(n) && n >= 0 ? Math.min(n, 40) : null
}

export function FilterSheet({ value, defaults, jobTypes, regions, focus, onSave, onClose }: {
  value: Filters
  defaults: Filters
  jobTypes: JobType[]
  regions: string[]
  focus: FilterSection
  onSave: (f: Filters) => void
  onClose: () => void
}) {
  const [draft, setDraft] = useState<Filters>(value)
  const jobs = draft.job_types ?? []
  const types = draft.company_types ?? []
  const picked = draft.regions ?? []

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.getElementById(`filter-${focus}`)?.scrollIntoView({ block: 'nearest' })
    return () => window.removeEventListener('keydown', onKey)
  }, [focus, onClose])

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="필터" onClick={(e) => e.stopPropagation()}>
        <section id="filter-jobs" className="sheet-section">
          <h2>{copy.filter.jobTypes}</h2>
          <div className="chips wrap">
            {jobTypes.map((j) => (
              <button key={j.id} type="button" className={jobs.includes(j.id) ? 'chip selected' : 'chip'} aria-pressed={jobs.includes(j.id)}
                onClick={() => setDraft({ ...draft, job_types: toggle(jobs, j.id) })}>
                {j.name}
              </button>
            ))}
          </div>
        </section>
        <section id="filter-types" className="sheet-section">
          <h2>{copy.filter.companyTypes}</h2>
          <div className="chips wrap">
            {TYPES.map((t) => (
              <button key={t} type="button" className={types.includes(t) ? 'chip selected' : 'chip'} aria-pressed={types.includes(t)}
                onClick={() => setDraft({ ...draft, company_types: toggle(types, t) })}>
                {t}
              </button>
            ))}
          </div>
        </section>
        <section id="filter-career" className="sheet-section">
          <h2>{copy.filter.career}</h2>
          <div className="range">
            <input inputMode="numeric" aria-label="최소 연차" value={draft.career?.min ?? ''}
              onChange={(e) => setDraft({ ...draft, career: { ...draft.career, min: num(e.target.value) } })} />
            <span>~</span>
            <input inputMode="numeric" aria-label="최대 연차" value={draft.career?.max ?? ''}
              onChange={(e) => setDraft({ ...draft, career: { ...draft.career, max: num(e.target.value) } })} />
            <span>년</span>
          </div>
        </section>
        <section id="filter-regions" className="sheet-section">
          <h2>{copy.filter.regions}</h2>
          <div className="chips wrap">
            {regions.map((r) => (
              <button key={r} type="button" className={picked.includes(r) ? 'chip selected' : 'chip'} aria-pressed={picked.includes(r)}
                onClick={() => setDraft({ ...draft, regions: toggle(picked, r) })}>
                {r}
              </button>
            ))}
          </div>
        </section>
        <div className="sheet-actions">
          <button type="button" className="btn" onClick={() => setDraft(defaults)}>{copy.filter.reset}</button>
          <button type="button" className="btn primary" onClick={() => onSave(draft)}>{copy.filter.save}</button>
        </div>
      </div>
    </div>
  )
}
