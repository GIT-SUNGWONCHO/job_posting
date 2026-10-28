import { useId, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { useApps } from '../lib/applications'
import { companyLine, deadlineText, isUrgent, listTitle } from '../lib/format'
import { href } from '../lib/route'
import type { Match } from '../lib/matches'
import type { Company, Posting } from '../lib/types'

export function Deadline({ p, today }: { p: Posting; today: string }) {
  const urgent = isUrgent(p, today)
  return <span className={urgent ? 'dday urgent' : 'dday'}>{deadlineText(p, today)}</span>
}

export function Score({ value, solid = false }: { value: number; solid?: boolean }) {
  const size = solid ? 56 : 44
  return (
    <span className={solid ? 'score solid' : 'score'} style={{ width: size, height: size }} aria-label={`점수 ${value}`}>
      {value}
    </span>
  )
}

/** 메타 줄의 얇은 세로선 */
export const Sep = () => <span className="sep" aria-hidden="true" />

/** 공고 한 줄: 회사 · 그룹(배지는 회사 이름 뒤에 하나) / 목록 제목 한 줄 / 마감 | 경력. 점수는 오른쪽 상자에 숫자만 */
export function JobRow({ p, c, today, showCompany = true, active = false, match, badge }: {
  p: Posting
  c: Company | undefined
  today: string
  showCompany?: boolean
  active?: boolean
  match?: Match
  /** 회사 이름 뒤의 배지(홈의 "오늘"). 지원 단계가 있으면 그것이 먼저 */
  badge?: string
}) {
  const stage = useApps().get(p.id)?.stage
  const mark = stage
    ? <span className={stage === 'dismissed' ? 'badge muted' : 'badge'}>{copy.apply.short[stage]}</span>
    : badge && <span className="badge">{badge}</span>
  return (
    <a className={active ? 'row active' : 'row'} href={href.job(p.id)} aria-current={active ? 'page' : undefined}>
      <span className="row-main">
        {showCompany ? <span className="row-company"><span>{companyLine(c, p.company)}</span>{mark}</span> : mark && <span className="row-company">{mark}</span>}
        <span className="row-title">{listTitle(p)}</span>
        <span className="row-meta">
          <Deadline p={p} today={today} />
          <Sep />
          <span>{p.career}</span>
          {p.headhunter && <><Sep /><span>{copy.job.headhunter}</span></>}
        </span>
      </span>
      {match && (
        <span className="row-score">
          <Score value={match.score} />
          {match.mine && <span className="mine" aria-label={copy.match.labels[match.mine]}>{copy.match.marks[match.mine]}</span>}
        </span>
      )}
    </a>
  )
}

const INFO_ICON = <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 7.6v.1" /></svg>

// 선 아이콘(색은 글자색, 굵기는 app.css .ico)
export const SEARCH_ICON = <svg className="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>
export const SLIDERS_ICON = <svg className="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></svg>
export const DOWN_ICON = <svg className="ico down" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
export const RIGHT_ICON = <svg className="ico right" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
export const BACK_ICON = <svg className="ico back" viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg>
export const STAR_ICON = <svg className="ico star" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.2l2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 16.6l-4.8 2.5.9-5.4-3.9-3.8 5.4-.8z" /></svg>

/** 섹션 머리: 제목 · 회색 숫자 · 오른쪽(ⓘ 기준, 출처 등). 기준 설명은 ⓘ를 눌러야 아래에 보인다 */
export function SectionTitle({ children, count, info, right }: {
  children: ReactNode
  count?: number | string
  /** ⓘ를 누르면 보이는 기준 설명 */
  info?: ReactNode
  right?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <>
      <div className="section-title">
        <h2>{children}</h2>
        {count !== undefined && <span className="count">{typeof count === 'number' ? count.toLocaleString() : count}</span>}
        {(info || right) && (
          <span className="right">
            {right}
            {info && (
              <button type="button" className="info-btn" aria-label={copy.common.info} aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
                {INFO_ICON}
              </button>
            )}
          </span>
        )}
      </div>
      {info && open && <p className="info-note" id={id}>{info}</p>}
    </>
  )
}

export function Chip({ selected, onClick, children }: { selected?: boolean; onClick?: () => void; children: ReactNode }) {
  return (
    <button type="button" className={selected ? 'chip selected' : 'chip'} aria-pressed={selected} onClick={onClick}>
      {children}
    </button>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}
