import { copy } from '../copy'
import { JobRow, SectionTitle } from '../components/ui'
import { goBack, href } from '../lib/route'
import type { Screen } from '../lib/types'

export function CompanyPage({ screen, companyKey, today, panel = false }: {
  screen: Screen
  companyKey: string
  today: string
  panel?: boolean
}) {
  const c = screen.companies[companyKey]
  const open = screen.postings.filter((p) => p.company === companyKey && !p.noise)
  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && (
        <div className="topbar">
          <button type="button" className="icon-btn" aria-label={copy.job.back} onClick={() => goBack(href.companies)}>‹</button>
        </div>
      )}
      <header className="page-head company-head">
        <span className="logo" aria-hidden="true">{(c?.name ?? companyKey).slice(0, 1)}</span>
        <div>
          <h1>{c?.name ?? companyKey}</h1>
          <div className="page-sub">{[c?.group && `${c.group} 계열`, c?.type].filter(Boolean).join(' · ')}</div>
        </div>
      </header>
      <section className="section">
        <SectionTitle right={<span className="count">{copy.company.daily}</span>}>{copy.company.hiring}</SectionTitle>
        <div className="sub-head">{copy.jobs.openCount(open.length)}</div>
        <div className="rows">
          {open.map((p) => <JobRow key={p.id} p={p} c={c} today={today} showCompany={false} />)}
        </div>
      </section>
    </div>
  )
}
