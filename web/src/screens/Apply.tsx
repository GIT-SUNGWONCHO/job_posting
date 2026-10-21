import { useState } from 'react'
import { copy } from '../copy'
import { Deadline, Empty, SectionTitle } from '../components/ui'
import { STAGES, upcoming, type Application, type Stage } from '../lib/applications'
import { dateText } from '../lib/format'
import { href } from '../lib/route'
import type { Posting, Screen } from '../lib/types'

const t = copy.apply
const SHOW = 3

// 지원 현황(와이어프레임 M6): 단계별 숫자, 다가오는 일정, 단계별 목록. 관심 없음은 맨 아래 접어 둔다
export function Apply({ screen, apps, today }: { screen: Screen; apps: Map<string, Application>; today: string }) {
  const [counts, groups] = group(apps)
  const open = new Map(screen.postings.map((p) => [p.id, p]))
  const soon = upcoming(apps.values(), today)

  return (
    <div className="page">
      <header className="page-head">
        <h1>{t.title}</h1>
        <div className="stage-boxes">
          {STAGES.map((s) => (
            <a key={s} href={`#stage-${s}`} className="stage-box"
              onClick={(e) => { e.preventDefault(); document.getElementById(`stage-${s}`)?.scrollIntoView({ behavior: 'smooth' }) }}>
              <b>{counts[s]}</b>{t.short[s]}
            </a>
          ))}
        </div>
      </header>

      {apps.size === 0 ? <Empty>{t.empty}</Empty> : (
        <>
          <section className="section">
            <SectionTitle>{t.upcoming}</SectionTitle>
            {soon.length === 0 ? <p className="note">{t.noUpcoming}</p> : soon.map((u) => (
              <a key={u.postingId + u.what} className="upcoming" href={open.has(u.postingId) ? href.job(u.postingId) : undefined}>
                <b className={u.date === today ? 'urgent' : undefined}>{u.date === today ? t.today : dateText(u.date)}</b>
                <span>{u.what === 'deadline' ? t.deadlineOf(u.company) : t.nextOf(u.company, u.label)}</span>
              </a>
            ))}
          </section>
          {STAGES.map((s) => groups[s].length > 0 && (
            <StageList key={s} stage={s} list={groups[s]} open={open} today={today} />
          ))}
          {groups.dismissed.length > 0 && (
            <section className="section">
              <details>
                <summary className="section-title"><h2>{t.long.dismissed} <span className="count">{groups.dismissed.length}</span></h2></summary>
                <p className="note">{t.dismissedNote}</p>
                <div className="rows">
                  {groups.dismissed.map((a) => <AppRow key={a.postingId} a={a} posting={open.get(a.postingId)} today={today} />)}
                </div>
              </details>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function group(apps: Map<string, Application>): [Record<Stage, number>, Record<Stage, Application[]>] {
  const groups = { interest: [], applied: [], passed: [], interview: [], result: [], dismissed: [] } as Record<Stage, Application[]>
  for (const a of apps.values()) groups[a.stage].push(a)
  // 관심은 마감이 가까운 순, 나머지는 그 단계로 옮긴 날이 최근인 순
  const key = (a: Application) => (a.snapshot.deadlineType === 'date' && a.snapshot.deadline ? a.snapshot.deadline : '9999')
  groups.interest.sort((a, b) => key(a).localeCompare(key(b)))
  for (const s of ['applied', 'passed', 'interview', 'result', 'dismissed'] as Stage[]) {
    groups[s].sort((a, b) => (b.dates[s] ?? '').localeCompare(a.dates[s] ?? ''))
  }
  const counts = Object.fromEntries(Object.entries(groups).map(([s, l]) => [s, l.length])) as Record<Stage, number>
  return [counts, groups]
}

function StageList({ stage, list, open, today }: {
  stage: Stage
  list: Application[]
  open: Map<string, Posting>
  today: string
}) {
  const [all, setAll] = useState(false)
  const shown = all ? list : list.slice(0, SHOW)
  return (
    <section className="section" id={`stage-${stage}`}>
      <SectionTitle right={<span className="count">{list.length}</span>}>{t.long[stage]}</SectionTitle>
      <div className="rows">
        {shown.map((a) => <AppRow key={a.postingId} a={a} posting={open.get(a.postingId)} today={today} />)}
      </div>
      {list.length > SHOW && !all && (
        <button type="button" className="text-link" onClick={() => setAll(true)}>{t.more(list.length - SHOW)}</button>
      )}
    </section>
  )
}

/** 한 줄: 회사 / 공고 제목 / 단계에 맞는 보조 정보(관심: 마감, 지원 이후: 지원한 날·결과·메모). 마감돼 빠진 공고는 원문으로 */
function AppRow({ a, posting, today }: { a: Application; posting: Posting | undefined; today: string }) {
  const s = a.snapshot
  const meta: string[] = []
  if (a.stage !== 'interest' && a.dates.applied) meta.push(t.appliedOn(dateText(a.dates.applied)))
  if (a.stage === 'result' && a.outcome) meta.push(t.outcomes[a.outcome])
  if (a.nextOn && a.nextOn >= today) meta.push(`${t.nextOf('', a.nextLabel).trim()} ${dateText(a.nextOn)}`)
  if (a.memo) meta.push(t.hasMemo)
  if (!posting) meta.push(t.closed)
  const link = posting ? href.job(a.postingId) : s.url ?? undefined
  return (
    <a className="row" href={link} target={posting ? undefined : '_blank'} rel={posting ? undefined : 'noreferrer noopener'}>
      <span className="row-main">
        <span className="row-company">{s.company}</span>
        <span className="row-title">{s.title}</span>
        <span className="row-meta">
          {a.stage === 'interest' && posting && <Deadline p={posting} today={today} />}
          {meta.map((m) => <span key={m}>{m}</span>)}
        </span>
      </span>
    </a>
  )
}
