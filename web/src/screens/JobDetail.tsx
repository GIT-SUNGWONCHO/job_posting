import { useEffect, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { Deadline, SectionTitle } from '../components/ui'
import { companyLine, dateText } from '../lib/format'
import { goBack, href } from '../lib/route'
import { loadBody } from '../lib/load'
import type { Body, Posting, Screen } from '../lib/types'

// 본문의 소제목(담당업무, 자격요건 등). 수집처마다 [대괄호]나 이모지가 붙기도 한다
const HEADING = /^(\p{Extended_Pictographic}\s*)?\[?(소개|포지션 소개|회사 소개|담당\s*업무|주요\s*업무|자격\s*요건|필수\s*요건|우대\s*사항|혜택\s*및\s*복지|복지\s*및\s*혜택|채용\s*절차|전형\s*절차|근무\s*조건|근무\s*환경|기타\s*사항|유의\s*사항|보상|접수\s*방법|마감\s*기한|사내\s*문화)\]?$/u

export function JobDetail({ screen, posting, today, panel = false }: {
  screen: Screen
  posting: Posting | undefined
  today: string
  panel?: boolean
}) {
  const [body, setBody] = useState<{ id: string; body: Body | null; failed?: boolean } | null>(null)
  useEffect(() => {
    if (!posting?.hasBody) return
    let alive = true
    const id = posting.id
    loadBody(id).then(
      (b) => alive && setBody({ id, body: b }),
      () => alive && setBody({ id, body: null, failed: true }),
    )
    return () => {
      alive = false
    }
  }, [posting])

  if (!posting) return <div className="page"><p className="empty">{copy.jobs.empty}</p></div>
  const p = posting
  const shown = body?.id === p.id ? body : null
  const c = screen.companies[p.company]
  const jobName = screen.jobTypes?.find((j) => j.id === p.jobType)?.name
  const rows: [string, ReactNode][] = [
    ...(jobName ? [[copy.job.jobType, jobName] as [string, ReactNode]] : []),
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
      <section className="section">
        <SectionTitle right={shown?.body && <span className="count">{copy.job.bodySource[shown.body.source] ?? ''}</span>}>
          {copy.job.body}
        </SectionTitle>
        {!p.hasBody && <p className="note body-note">{copy.job.noBody}</p>}
        {p.hasBody && !shown && <p className="note body-note">{copy.load.loading}</p>}
        {shown?.failed && <p className="note body-note">{copy.job.bodyFailed}</p>}
        {shown?.body && (
          <div className="body-text">
            {shown.body.text.split('\n').map((line, i) =>
              HEADING.test(line.trim()) ? <h3 key={i}>{line.trim().replace(/^\[|\]$/g, '')}</h3> : <p key={i}>{line}</p>,
            )}
          </div>
        )}
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
