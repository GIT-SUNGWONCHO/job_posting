import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { BACK_ICON, Deadline, DOWN_ICON, RIGHT_ICON, SectionTitle, Sep } from '../components/ui'
import type { Application } from '../lib/applications'
import type { Feedback } from '../lib/feedback'
import { ApplySection, InterestButton } from './ApplySection'
import { Basis, MyRating, Verdict } from './MatchSection'
import { dateText } from '../lib/format'
import { goBack, href } from '../lib/route'
import { loadBody } from '../lib/load'
import { useMatchDetail, type Match } from '../lib/matches'
import type { Body, Posting, Screen } from '../lib/types'

// 본문의 소제목(담당업무, 자격요건 등). 수집처마다 [대괄호]나 이모지가 붙기도 한다
const HEADING = /^(\p{Extended_Pictographic}\s*)?\[?(소개|포지션 소개|회사 소개|담당\s*업무|주요\s*업무|자격\s*요건|필수\s*요건|우대\s*사항|혜택\s*및\s*복지|복지\s*및\s*혜택|채용\s*절차|전형\s*절차|근무\s*조건|근무\s*환경|기타\s*사항|유의\s*사항|보상|접수\s*방법|마감\s*기한|사내\s*문화)\]?$/u


export function JobDetail({ screen, posting, today, match, feedback, onFeedback, app, onApp, showRating = true, panel = false }: {
  screen: Screen
  posting: Posting | undefined
  today: string
  match?: Match
  feedback?: Feedback
  onFeedback: (postingId: string, f: Feedback) => void
  app?: Application
  onApp: (postingId: string, app: Application | null) => void
  /** 개발용 내 평가 칸(관리에서 끌 수 있다) */
  showRating?: boolean
  panel?: boolean
}) {
  // 열린 공고에 없으면 대개 수집처에서 내려간 공고다(지우지 않고 회사 화면 지난 공고에 남는다)
  if (!posting) {
    return (
      <div className={panel ? 'page detail panel' : 'page detail'}>
        {!panel && <TopBar />}
        <p className="empty">{copy.job.gone}</p>
        <div className="list-more"><a className="btn block" href={href.jobs}>{copy.job.toJobs}</a></div>
      </div>
    )
  }
  return <Detail screen={screen} p={posting} today={today} match={match} feedback={feedback} onFeedback={onFeedback} app={app} onApp={onApp} showRating={showRating} panel={panel} />
}

function TopBar() {
  return (
    <div className="topbar">
      <button type="button" className="icon-btn" aria-label={copy.common.back} onClick={() => goBack(href.jobs)}>{BACK_ICON}</button>
    </div>
  )
}

function Detail({ screen, p, today, match, feedback, onFeedback, app, onApp, showRating, panel }: {
  screen: Screen
  p: Posting
  today: string
  match?: Match
  feedback?: Feedback
  onFeedback: (postingId: string, f: Feedback) => void
  app?: Application
  onApp: (postingId: string, app: Application | null) => void
  showRating: boolean
  panel: boolean
}) {
  const [body, setBody] = useState<{ id: string; body: Body | null; failed?: boolean } | null>(null)
  const [bodyOpen, setBodyOpen] = useState(false)
  const [stageOpen, setStageOpen] = useState(false)
  useEffect(() => {
    if (!p.hasBody) return
    let alive = true
    const id = p.id
    loadBody(id).then(
      (b) => alive && setBody({ id, body: b }),
      () => alive && setBody({ id, body: null, failed: true }),
    )
    return () => {
      alive = false
    }
  }, [p])
  const detail = useMatchDetail(p.id, !!match)
  const shown = body?.id === p.id ? body : null
  const c = screen.companies[p.company]
  const company = c?.name ?? p.company
  const jobName = screen.jobTypes?.find((j) => j.id === p.jobType)?.name
  const links = p.sources.filter((s) => s.url)
  const rows: [string, ReactNode][] = [
    [copy.job.deadline, <Fragment key="dl"><Deadline p={p} today={today} />{p.deadline && <span className="muted"> · {dateText(p.deadline, true)}</span>}</Fragment>],
    [copy.job.career, p.career],
    ...(jobName ? [[copy.job.jobType, jobName] as [string, ReactNode]] : []),
    [copy.job.work, <span key="work" className="inline-meta">{p.regions.join(', ') || '-'}{p.employment.length > 0 && <><Sep />{p.employment.join(', ')}</>}</span>],
    [copy.job.firstSeen, <Fragment key="seen">{dateText(p.firstSeen)}<span className="muted"> · {p.sources.map((s) => s.name).join(' · ')}</span></Fragment>],
  ]
  const stageLabel = app ? copy.apply.long[app.stage] : copy.apply.none
  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && <TopBar />}
      <header className="detail-head">
        <a className="detail-company" href={href.company(p.company)}>{[company, c?.type].filter(Boolean).join(' · ')}{RIGHT_ICON}</a>
        <h1 className="detail-title">{p.title}</h1>
        <div className="kv2">
          {rows.map(([k, v]) => <Fragment key={k}><span className="k">{k}</span><span className="v">{v}</span></Fragment>)}
          <span className="k">{copy.apply.stage}</span>
          <button type="button" className="v stage-pick" aria-expanded={stageOpen} onClick={() => setStageOpen(!stageOpen)}>
            {stageLabel}<span className={stageOpen ? 'chev up' : 'chev'}>{DOWN_ICON}</span>
          </button>
        </div>
        {stageOpen && <ApplySection key={p.id} postingId={p.id} posting={p} company={company} app={app} today={today} onChange={onApp} embedded />}
      </header>
      {match && <Verdict match={match} />}
      {detail && <Basis detail={detail} fit={screen.matchFit} />}
      <section className="section">
        <SectionTitle right={shown?.body && <span className="count">{copy.job.bodySource[shown.body.source] ?? ''}</span>}>
          {copy.job.body}
        </SectionTitle>
        {!p.hasBody && <p className="note">{copy.job.noBody}</p>}
        {p.hasBody && !shown && <p className="note">{copy.load.loading}</p>}
        {shown?.failed && <p className="note">{copy.job.bodyFailed}</p>}
        {shown?.body && (
          <>
            <div className={bodyOpen ? 'body-text' : 'body-text folded'}>
              {shown.body.text.split('\n').map((line, i) =>
                HEADING.test(line.trim()) ? <h3 key={i}>{line.trim().replace(/^\[|\]$/g, '')}</h3> : <p key={i}>{line}</p>,
              )}
            </div>
            {!bodyOpen && <button type="button" className="btn block more" onClick={() => setBodyOpen(true)}>{copy.job.bodyMore}</button>}
          </>
        )}
        {links.length > 1 && (
          <div className="source-links">
            {links.slice(1).map((s) => <a key={s.source} className="text-link" href={s.url ?? undefined} target="_blank" rel="noreferrer noopener">{copy.job.openAt(s.name)} ↗</a>)}
          </div>
        )}
      </section>
      {showRating && match && detail && (
        <MyRating postingId={p.id} posting={{ company, title: p.title }} detail={detail} feedback={feedback} onFeedback={onFeedback} />
      )}
      <div className="action-bar">
        <InterestButton p={p} company={company} app={app} today={today} onApp={onApp} onOpen={() => setStageOpen(true)} />
        {links[0] && (
          <a className="btn primary" href={links[0].url ?? undefined} target="_blank" rel="noreferrer noopener">{copy.apply.openOriginal} ↗</a>
        )}
      </div>
    </div>
  )
}
