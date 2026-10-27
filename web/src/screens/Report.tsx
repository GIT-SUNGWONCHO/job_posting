import { useState } from 'react'
import { copy } from '../copy'
import { Deadline, Empty, JobRow, Score, SectionTitle } from '../components/ui'
import { NOT_AGAIN, useApps } from '../lib/applications'
import { addDays, companyLine, dateText, isUrgent } from '../lib/format'
import type { Match } from '../lib/matches'
import { href } from '../lib/route'
import { useStars } from '../lib/stars'
import type { Posting, Screen } from '../lib/types'

/** 이번 주: 오늘을 포함한 최근 며칠 */
const WEEK = 7
/** 이번 주 새 공고에 먼저 보일 줄 수(나머지는 더 보기) */
const WEEK_ROWS = 10
const SHOW = 5

// 오늘의 리포트: 이번 주 기준 네 덩어리. 위에서 보인 공고는 아래에서 뺀다(docs/content-rules.md "아침 알림·오늘의 리포트").
// 1 이번 주 1등 · 2 이번 주 새 공고 · 3 마감 임박 · 4 관심 회사 새 공고. 전체 점수순은 공고 탭(추천순)
export function Report({ screen, passed, today, matches }: {
  screen: Screen
  passed: Posting[]
  today: string
  matches: Map<string, Match>
}) {
  const [allWeek, setAllWeek] = useState(false)
  const apps = useApps()
  const stars = useStars().state
  const c = screen.companies
  const stageOf = (p: Posting) => apps.get(p.id)?.stage
  // 이미 지원했거나 관심 없음으로 둔 공고는 다시 보여주지 않는다
  const again = (p: Posting) => {
    const stage = stageOf(p)
    return !(stage && NOT_AGAIN.includes(stage))
  }
  const score = (p: Posting) => matches.get(p.id)?.score ?? -1
  // 점수 높은 순(점수 없는 공고는 뒤에), 같으면 최근에 올라온 공고 먼저
  const byScore = (a: Posting, b: Posting) => (score(b) - score(a)) || b.firstSeen.localeCompare(a.firstSeen)
  const byDeadline = (a: Posting, b: Posting) => (a.deadline ?? '').localeCompare(b.deadline ?? '')

  const weekStart = addDays(screen.date, -(WEEK - 1))
  const week = passed.filter((p) => p.firstSeen >= weekStart && again(p)).sort(byScore)
  const todayCount = week.filter((p) => p.firstSeen === screen.date).length
  // 1 이번 주 1등: 최근 7일 새 공고 중 점수 1등(점수가 있는 공고만)
  const top = week[0] && matches.has(week[0].id) ? week[0] : undefined
  // 2 이번 주 새 공고: 1등을 뺀 나머지
  const rest = top ? week.slice(1) : week
  const restShown = allWeek ? rest : rest.slice(0, WEEK_ROWS)
  const shown = new Set([...(top ? [top.id] : []), ...rest.slice(0, WEEK_ROWS).map((p) => p.id)])
  // 3 마감 임박: 관심 공고(필터와 상관없이) 먼저, 그다음 필터 통과 공고. 위에 보인 공고는 빼고
  const urgent = [
    ...screen.postings.filter((p) => stageOf(p) === 'interest' && isUrgent(p, today)).sort(byDeadline),
    ...passed.filter((p) => isUrgent(p, today) && stageOf(p) !== 'interest' && again(p)).sort(byDeadline),
  ].filter((p) => !shown.has(p.id))
  urgent.slice(0, SHOW).forEach((p) => shown.add(p.id))
  // 4 관심 회사 새 공고: ★ 회사의 이번 주 새 공고, 필터와 상관없이(잡음은 빼고). 위에 보인 공고는 빼고
  const starred = stars instanceof Set && stars.size
    ? screen.postings.filter((p) => stars.has(p.company) && p.firstSeen >= weekStart && !p.noise && again(p) && !shown.has(p.id)).sort(byScore)
    : []
  const badge = (p: Posting) => (p.firstSeen === screen.date ? copy.report.todayBadge : undefined)

  return (
    <div className="page">
      <header className="page-head">
        <h1>{copy.report.title}</h1>
        <div className="page-sub">{dateText(screen.date)}</div>
        <div className="summary">
          <span>{copy.report.weekCount} <b>{week.length.toLocaleString()}</b></span>
          <span>{copy.report.todayCount} <b>{todayCount}</b></span>
          <span>{copy.report.urgent} <b className="urgent">{urgent.length}</b></span>
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
                <span className="row-meta">
                  {badge(top) && <span className="stage-chip">{badge(top)}</span>}
                  <Deadline p={top} today={today} /><span>{top.career}</span>
                </span>
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

      <section className="section">
        <SectionTitle right={<span className="count">{copy.jobs.count(rest.length)}</span>}>{copy.report.weekSection}</SectionTitle>
        <p className="note small">{copy.report.weekNote(WEEK)}</p>
        {rest.length === 0 ? (
          <Empty>{top ? copy.report.noMoreWeek : copy.report.noWeek}</Empty>
        ) : (
          <div className="rows">
            {restShown.map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} badge={badge(p)} />)}
          </div>
        )}
        {rest.length > restShown.length && (
          <button type="button" className="text-link" onClick={() => setAllWeek(true)}>{copy.jobs.more(rest.length - restShown.length)}</button>
        )}
      </section>

      {urgent.length > 0 && (
        <section className="section">
          <SectionTitle right={<span className="count">{copy.jobs.count(urgent.length)}</span>}>{copy.report.urgentSection}</SectionTitle>
          <div className="rows">
            {urgent.slice(0, SHOW).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
          </div>
        </section>
      )}

      {starred.length > 0 && (
        <section className="section">
          <SectionTitle right={<span className="count">{copy.jobs.count(starred.length)}</span>}>{copy.report.starredSection}</SectionTitle>
          <div className="rows">
            {starred.slice(0, SHOW).map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} badge={badge(p)} />)}
          </div>
        </section>
      )}

      <section className="section">
        <a className="more-link" href={href.jobs}>{copy.report.allByScore} ›</a>
      </section>
    </div>
  )
}
