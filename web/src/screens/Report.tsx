import { copy } from '../copy'
import { Deadline, Empty, JobRow, Score, SectionTitle } from '../components/ui'
import { NOT_AGAIN, useApps } from '../lib/applications'
import { addDays, companyLine, dateText, isUrgent } from '../lib/format'
import type { Match } from '../lib/matches'
import { href } from '../lib/route'
import { useStars } from '../lib/stars'
import type { Posting, Screen } from '../lib/types'

const SHOW = 5
const HERO_ROWS = 3
/** 이번 주 올라온 공고: 오늘을 포함한 최근 며칠 */
const WEEK = 7

export function Report({ screen, passed, today, matches }: {
  screen: Screen
  passed: Posting[]
  today: string
  matches: Map<string, Match>
}) {
  const apps = useApps()
  const stars = useStars().state
  const stageOf = (p: Posting) => apps.get(p.id)?.stage
  // 이미 지원했거나 관심 없음으로 둔 공고는 다시 추천하지 않는다
  const again = (p: Posting) => {
    const stage = stageOf(p)
    return !(stage && NOT_AGAIN.includes(stage))
  }
  const fresh = passed.filter((p) => p.firstSeen === screen.date)
  // 마감 임박: 관심 공고(필터와 상관없이) 먼저, 그다음 필터 통과 공고. 지원했거나 관심 없음은 뺀다(아침 알림과 같게)
  const byDeadline = (a: Posting, b: Posting) => (a.deadline ?? '').localeCompare(b.deadline ?? '')
  const interest = screen.postings.filter((p) => stageOf(p) === 'interest' && isUrgent(p, today)).sort(byDeadline)
  const urgent = [
    ...interest,
    ...passed.filter((p) => isUrgent(p, today) && stageOf(p) !== 'interest' && again(p)).sort(byDeadline),
  ]
  // 관심 회사 새 공고: 필터와 상관없이(잡음, 지원했거나 관심 없음은 빼고). 위 "오늘 올라온 공고"에 보인 것은 빼고(아침 알림과 같게)
  const shown = new Set(fresh.slice(0, HERO_ROWS).map((p) => p.id))
  const starred = stars instanceof Set && stars.size
    ? screen.postings.filter((p) => stars.has(p.company) && p.firstSeen === screen.date && !p.noise && again(p) && !shown.has(p.id))
      .sort((a, b) => (matches.get(b.id)?.score ?? -1) - (matches.get(a.id)?.score ?? -1))
    : []
  const c = screen.companies
  // 오늘의 1등: 점수 가장 높은 공고(같으면 새 공고 먼저). 다음 추천은 그다음 4건
  const ranked = passed
    .filter((p) => matches.has(p.id) && again(p))
    .sort((a, b) => (matches.get(b.id)!.score - matches.get(a.id)!.score) || (b.firstSeen.localeCompare(a.firstSeen)))
  const top = ranked[0]
  const next = ranked.slice(1, 5)
  // 이번 주 올라온 공고: 최근 7일 처음 본 필터 통과 공고를 점수 높은 순(점수 없는 공고는 뒤에 최신순)
  const weekStart = addDays(screen.date, -(WEEK - 1))
  const week = passed
    .filter((p) => p.firstSeen >= weekStart && again(p))
    .sort((a, b) => ((matches.get(b.id)?.score ?? -1) - (matches.get(a.id)?.score ?? -1)) || b.firstSeen.localeCompare(a.firstSeen))

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
        <section className="hero hero-top-pick">
          <a className="hero-link" href={href.job(top.id)}>
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
          <div className="hero-actions">
            <a className="btn small" href={href.company(top.company)}>{copy.report.companyInfo}</a>
            <a className="btn small primary" href={href.job(top.id)}>{copy.report.detail}</a>
          </div>
        </section>
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

      <section className="section">
        <SectionTitle right={<span className="count">{copy.jobs.count(week.length)}</span>}>{copy.report.weekSection}</SectionTitle>
        <p className="note small">{copy.report.weekNote(WEEK)}</p>
        {week.length === 0 ? (
          <Empty>{copy.report.noWeek}</Empty>
        ) : (
          <div className="rows">
            {week.slice(0, SHOW).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
          </div>
        )}
      </section>

      {starred.length > 0 && (
        <section className="section">
          <SectionTitle right={<span className="count">{copy.jobs.count(starred.length)}</span>}>
            {copy.report.starredSection}
          </SectionTitle>
          <div className="rows">
            {starred.slice(0, SHOW).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
          </div>
        </section>
      )}

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

