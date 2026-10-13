import type { ReactNode } from 'react'
import { copy } from '../copy'
import { Deadline } from '../components/ui'
import { companyLine, dateText } from '../lib/format'
import { goBack, href } from '../lib/route'
import type { Posting, Screen } from '../lib/types'

export function JobDetail({ screen, posting, today, panel = false }: {
  screen: Screen
  posting: Posting | undefined
  today: string
  panel?: boolean
}) {
  if (!posting) return <div className="page"><p className="empty">{copy.jobs.empty}</p></div>
  const p = posting
  const c = screen.companies[p.company]
  const rows: [string, ReactNode][] = [
    [copy.job.deadline, <><Deadline p={p} today={today} />{p.deadline && <span className="muted"> · {dateText(p.deadline, true)}</span>}</>],
    [copy.job.career, p.career],
    [copy.job.regions, p.regions.join(', ') || '-'],
    [copy.job.employment, p.employment.join(', ') || '-'],
    [copy.job.firstSeen, dateText(p.firstSeen, true)],
  ]
  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && (
        <div className="topbar">
          <button type="button" className="icon-btn" aria-label={copy.job.back} onClick={() => goBack(href.jobs)}>‹</button>
        </div>
      )}
      <header className="page-head">
        <a className="detail-company" href={href.company(p.company)}>
          {companyLine(c, p.company)} ›
        </a>
        <h1>{p.title}</h1>
      </header>
      <section className="section">
        <dl className="kv">
          {rows.map(([k, v]) => (
            <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
          ))}
        </dl>
      </section>
      <section className="section actions">
        {p.sources.filter((s) => s.url).map((s, i) => (
          <a key={s.source} className={i === 0 ? 'btn primary' : 'btn'} href={s.url ?? undefined} target="_blank" rel="noreferrer noopener">
            {copy.job.openAt(s.name)} ↗
          </a>
        ))}
      </section>
    </div>
  )
}
