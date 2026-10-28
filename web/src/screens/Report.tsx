import { useEffect, useState } from 'react'
import { copy } from '../copy'
import { Deadline, Empty, JobRow, Score, SectionTitle, Sep } from '../components/ui'
import { NOT_AGAIN, useApps } from '../lib/applications'
import { addDays, companyLine, isUrgent, listTitle } from '../lib/format'
import { loadMatchDetail, type Match, type MatchDetail } from '../lib/matches'
import { href } from '../lib/route'
import { useStars } from '../lib/stars'
import type { Posting, Screen } from '../lib/types'

/** 이번 주: 오늘을 포함한 최근 며칠 */
const WEEK = 7
/** 이번 주 새 공고에 먼저 보일 줄 수(나머지는 더 보기) */
const WEEK_ROWS = 10
const SHOW = 5

// 오늘의 리포트: 이번 주 기준 네 덩어리. 위에서 보인 공고는 아래에서 뺀다(docs/content-rules.md "아침 알림·오늘의 리포트").
// 1 오늘의 1등 · 2 이번 주 새 공고 · 3 마감 임박 · 4 관심 회사 새 공고. 전체 점수순은 공고 탭(추천순)
export function Report({ screen, passed, today, matches }: {
  screen: Screen
  passed: Posting[]
  today: string
  matches: Map<string, Match>
}) {
  // 섹션마다 더 보기를 눌렀는지
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const take = (key: string, list: Posting[], n: number) => (open[key] ? list : list.slice(0, n))
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
  // "오늘"은 브라우저 날짜 기준(오늘 수집이 끝나기 전이면 어제 공고에 붙지 않게)
  const todayCount = week.filter((p) => p.firstSeen === today).length
  // 1 오늘의 1등: 최근 7일 새 공고 중 점수 1등(점수가 있는 공고만)
  const top = week[0] && matches.has(week[0].id) ? week[0] : undefined
  // 2 이번 주 새 공고: 1등을 뺀 나머지
  const rest = top ? week.slice(1) : week
  const restShown = take('week', rest, WEEK_ROWS)
  // 위에서 보인 공고(펼친 것까지)는 아래 섹션에서 뺀다
  const shown = new Set([...(top ? [top.id] : []), ...restShown.map((p) => p.id)])
  // 3 마감 임박: 관심 공고(필터와 상관없이) 먼저, 그다음 필터 통과 공고. 머리 건수는 빼기 전 전부
  const urgentAll = [
    ...screen.postings.filter((p) => stageOf(p) === 'interest' && isUrgent(p, today)).sort(byDeadline),
    ...passed.filter((p) => isUrgent(p, today) && stageOf(p) !== 'interest' && again(p)).sort(byDeadline),
  ]
  const urgent = urgentAll.filter((p) => !shown.has(p.id))
  const urgentShown = take('urgent', urgent, SHOW)
  urgentShown.forEach((p) => shown.add(p.id))
  // 4 관심 회사 새 공고: ★ 회사의 이번 주 새 공고, 필터와 상관없이(잡음은 빼고)
  const starred = stars instanceof Set && stars.size
    ? screen.postings.filter((p) => stars.has(p.company) && p.firstSeen >= weekStart && !p.noise && again(p) && !shown.has(p.id)).sort(byScore)
    : []
  const starredShown = take('starred', starred, SHOW)
  const badge = (p: Posting) => (p.firstSeen === today ? copy.report.todayBadge : undefined)
  const more = (key: string, list: Posting[], visible: Posting[]) => list.length > visible.length && (
    <button type="button" className="btn block more" onClick={() => setOpen({ ...open, [key]: true })}>{copy.jobs.more(list.length - visible.length)}</button>
  )
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div className="page home">
      <div className="home-head">
        <h1>{copy.report.title[0]}<br />{copy.report.title[1]}</h1>
        <div className="summary-strip">
          <button type="button" onClick={() => jump('home-week')}><span>{copy.report.weekCount}</span><b>{week.length.toLocaleString()}</b></button>
          <button type="button" onClick={() => jump('home-week')}><span>{copy.report.todayCount}</span><b>{todayCount}</b></button>
          <button type="button" onClick={() => jump('home-urgent')}><span>{copy.report.urgent}</span><b className="urgent">{urgentAll.length}</b></button>
        </div>
      </div>

      <div className="stack">
        {top && <TopPick p={top} screen={screen} today={today} match={matches.get(top.id)!} badge={badge(top)} />}

        <section id="home-week">
          <SectionTitle count={rest.length} info={copy.report.weekNote(WEEK)}>{copy.report.weekSection}</SectionTitle>
          {rest.length === 0 ? (
            <Empty>{top ? copy.report.noMoreWeek : copy.report.noWeek}</Empty>
          ) : (
            <div className="rows">
              {restShown.map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} badge={badge(p)} />)}
            </div>
          )}
          {more('week', rest, restShown)}
        </section>

        {urgent.length > 0 && (
          <section id="home-urgent">
            <SectionTitle count={urgent.length} info={copy.report.urgentNote}>{copy.report.urgentSection}</SectionTitle>
            <div className="rows">
              {urgentShown.map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} />)}
            </div>
            {more('urgent', urgent, urgentShown)}
          </section>
        )}

        {starred.length > 0 && (
          <section>
            <SectionTitle count={starred.length} info={copy.report.starredNote}>{copy.report.starredSection}</SectionTitle>
            <div className="rows">
              {starredShown.map((p) => <JobRow key={p.id} p={p} c={c[p.company]} today={today} match={matches.get(p.id)} badge={badge(p)} />)}
            </div>
            {more('starred', starred, starredShown)}
          </section>
        )}
      </div>
    </div>
  )
}

/** 오늘의 1등: 연한 파랑 카드에 회사 · 제목 · 진한 점수 상자, 맞는 점 · 부족한 점(판단 근거에서), 마감 | 경력, 버튼 둘 */
function TopPick({ p, screen, today, match, badge }: { p: Posting; screen: Screen; today: string; match: Match; badge?: string }) {
  const [detail, setDetail] = useState<{ id: string; d: MatchDetail | null } | null>(null)
  useEffect(() => {
    let alive = true
    loadMatchDetail(p.id).then((d) => alive && setDetail({ id: p.id, d }), () => alive && setDetail({ id: p.id, d: null }))
    return () => {
      alive = false
    }
  }, [p.id])
  const why = detail?.id === p.id && detail.d ? goodAndGap(detail.d) : null
  return (
    <section className="top-pick">
      <div className="top-label">{copy.report.top}</div>
      <div className="top-card">
        <a className="top-head" href={href.job(p.id)}>
          <span className="row-main">
            <span className="row-company"><span>{companyLine(screen.companies[p.company], p.company)}</span>{badge && <span className="badge">{badge}</span>}</span>
            <span className="hero-title">{listTitle(p)}</span>
          </span>
          <Score value={match.score} solid />
        </a>
        {why && (why.good || why.gap) ? (
          <div className="why">
            {why.good && <><span className="why-k good">{copy.report.good}</span><span className="why-v">{why.good}</span></>}
            {why.gap && <><span className="why-k">{copy.report.gap}</span><span className="why-v">{why.gap}</span></>}
          </div>
        ) : match.reason && <p className="match-reason">{match.reason}</p>}
        <span className="row-meta"><Deadline p={p} today={today} /><Sep /><span>{p.career}</span></span>
        <div className="top-actions">
          <a className="btn white" href={href.company(p.company)}>{copy.job.company}</a>
          <a className="btn primary" href={href.job(p.id)}>{copy.report.detail}</a>
        </div>
      </div>
    </section>
  )
}

/** 판단 근거에서 맞는 점(충족, 배점 큰 순 둘)과 부족한 점(미충족, 없으면 일부) */
function goodAndGap(d: MatchDetail): { good: string; gap: string } {
  const items = [...d.items].sort((a, b) => b.weight - a.weight)
  const names = (fit: string) => items.filter((it) => it.fit === fit).slice(0, 2).map((it) => it.name)
  const good = names('충족')
  const gap = names('미충족').length ? names('미충족') : names('일부')
  return { good: good.join(' · '), gap: gap.join(' · ') }
}
