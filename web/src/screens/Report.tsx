import { copy } from '../copy'
import { Deadline, Empty, JobRow, Score, SectionTitle } from '../components/ui'
import { NOT_AGAIN, useApps } from '../lib/applications'
import { mySlice, periodStats, sumSeries } from '../lib/career'
import { companyLine, dateText, isUrgent } from '../lib/format'
import type { Match } from '../lib/matches'
import { href } from '../lib/route'
import { useStars } from '../lib/stars'
import type { Filters, Posting, Screen } from '../lib/types'

const SHOW = 5
const HERO_ROWS = 3
/** 이번 주 커리어: 최근 며칠과 그 앞 같은 기간을 비교한다(아침 알림과 같게) */
const WEEK = 7

export function Report({ screen, passed, today, matches, filters }: {
  screen: Screen
  passed: Posting[]
  today: string
  matches: Map<string, Match>
  filters: Filters
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

      <Weekly screen={screen} filters={filters} />

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

/** 이번 주 커리어: 내 직무·기업 구분의 최근 7일 새 공고와 그 앞 7일 비교, 지금 열린 공고. 커리어 탭으로 잇는다 */
function Weekly({ screen, filters }: { screen: Screen; filters: Filters }) {
  const m = screen.career
  if (!m || m.days.length < 2) return null
  const stats = periodStats(sumSeries(m, mySlice(screen.jobTypes, filters)), WEEK)
  const { newSum, prevSum } = stats
  const change = prevSum === null
    ? copy.report.weeklyNoPrev(WEEK)
    : prevSum === 0
      ? copy.report.weeklyPrevZero(WEEK)
      : copy.report.weeklyChange(Math.round(((newSum - prevSum) / prevSum) * 100), WEEK)
  return (
    <section className="section">
      <SectionTitle right={<a className="more-link" href={href.career}>{copy.report.careerLink} ›</a>}>{copy.report.weekly}</SectionTitle>
      <div className="weekly">
        <div className="weekly-label">{copy.report.weeklyLabel(WEEK)}</div>
        <div className="weekly-value"><b>{newSum.toLocaleString()}</b>건</div>
        <div className="weekly-sub">
          <span>{change}</span>
          <span>{copy.report.weeklyOpen(stats.openNow)}</span>
        </div>
      </div>
    </section>
  )
}
