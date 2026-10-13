import { copy } from '../copy'
import { Deadline, Empty, JobRow, Score, SectionTitle } from '../components/ui'
import { companyLine, dateText, isUrgent } from '../lib/format'
import type { Match } from '../lib/matches'
import { href } from '../lib/route'
import type { Posting, Screen } from '../lib/types'

const SHOW = 5
const HERO_ROWS = 3

export function Report({ screen, passed, today, matches }: {
  screen: Screen
  passed: Posting[]
  today: string
  matches: Map<string, Match>
}) {
  const fresh = passed.filter((p) => p.firstSeen === screen.date)
  const urgent = passed
    .filter((p) => isUrgent(p, today))
    .sort((a, b) => (a.deadline ?? '').localeCompare(b.deadline ?? ''))
  const c = screen.companies
  // 오늘의 1등: 점수 가장 높은 공고(같으면 새 공고 먼저). 다음 추천은 그다음 4건
  const ranked = passed
    .filter((p) => matches.has(p.id))
    .sort((a, b) => (matches.get(b.id)!.score - matches.get(a.id)!.score) || (b.firstSeen.localeCompare(a.firstSeen)))
  const top = ranked[0]
  const next = ranked.slice(1, 5)

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

      {top && (
        <a className="hero hero-top-pick" href={href.job(top.id)}>
          <div className="hero-label">{copy.report.top}</div>
          <div className="match-head">
            <div className="row-main">
              <span className="row-company">{companyLine(c[top.company], top.company)}</span>
              <span className="hero-title">{top.title}</span>
              {matches.get(top.id)?.reason && <span className="row-reason">{matches.get(top.id)?.reason}</span>}
              <span className="row-meta"><Deadline p={top} today={today} /><span>{top.career}</span></span>
            </div>
            <Score value={matches.get(top.id)!.score} solid size={56} />
          </div>
        </a>
      )}

      {next.length > 0 && (
        <section className="section">
          <SectionTitle right={<a className="more-link" href={href.jobs}>{copy.report.seeAll} ›</a>}>{copy.report.next}</SectionTitle>
          <div className="rows">
            {next.map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
          </div>
        </section>
      )}

      <section className={top ? 'section' : 'hero'}>
        <div className="hero-top">
          <span className="hero-label">{copy.report.freshSection}</span>
          <a className="more-link" href={href.jobs}>{copy.report.seeAll} ›</a>
        </div>
        <div className="hero-count"><b>{fresh.length.toLocaleString()}</b>건</div>
        {fresh.length === 0 ? (
          <Empty>{copy.report.noFresh}</Empty>
        ) : (
          <div className="rows">
            {fresh.slice(0, HERO_ROWS).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
          </div>
        )}
      </section>

      {urgent.length > 0 && (
        <section className="section">
          <SectionTitle right={<span className="count">{copy.jobs.count(urgent.length)}</span>}>
            {copy.report.urgentSection}
          </SectionTitle>
          <div className="rows">
            {urgent.slice(0, SHOW).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
          </div>
        </section>
      )}
    </div>
  )
}
