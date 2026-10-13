import { copy } from '../copy'
import { Empty, JobRow, SectionTitle } from '../components/ui'
import { dateText, isUrgent } from '../lib/format'
import { href } from '../lib/route'
import type { Posting, Screen } from '../lib/types'

const SHOW = 5
const HERO_ROWS = 3

export function Report({ screen, passed, today }: { screen: Screen; passed: Posting[]; today: string }) {
  const fresh = passed.filter((p) => p.firstSeen === screen.date)
  const urgent = passed
    .filter((p) => isUrgent(p, today))
    .sort((a, b) => (a.deadline ?? '').localeCompare(b.deadline ?? ''))
  const c = screen.companies

  return (
    <div className="page">
      <header className="page-head">
        <h1>{copy.report.title}</h1>
        <div className="page-sub">{dateText(screen.date)}</div>
        <div className="summary">
          <span>{copy.report.passed} <b>{passed.length.toLocaleString()}</b></span>
          <span>{copy.report.urgent} <b className="urgent">{urgent.length}</b></span>
          <span>{copy.report.fresh} <b>{fresh.length}</b></span>
        </div>
      </header>

      <section className="hero">
        <div className="hero-top">
          <span className="hero-label">{copy.report.freshSection}</span>
          <a className="more-link" href={href.jobs}>{copy.report.seeAll} ›</a>
        </div>
        <div className="hero-count"><b>{fresh.length.toLocaleString()}</b>건</div>
        {fresh.length === 0 ? (
          <Empty>{copy.report.noFresh}</Empty>
        ) : (
          <div className="rows">
            {fresh.slice(0, HERO_ROWS).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} />)}
          </div>
        )}
      </section>

      {urgent.length > 0 && (
        <section className="section">
          <SectionTitle right={<span className="count">{copy.jobs.count(urgent.length)}</span>}>
            {copy.report.urgentSection}
          </SectionTitle>
          <div className="rows">
            {urgent.slice(0, SHOW).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} />)}
          </div>
        </section>
      )}
    </div>
  )
}
