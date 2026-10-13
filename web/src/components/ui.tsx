import type { ReactNode } from 'react'
import { copy } from '../copy'
import { companyLine, deadlineText, isUrgent } from '../lib/format'
import { href } from '../lib/route'
import type { Company, Posting } from '../lib/types'

export function Deadline({ p, today }: { p: Posting; today: string }) {
  const urgent = isUrgent(p, today)
  return <span className={urgent ? 'dday urgent' : 'dday'}>{deadlineText(p, today)}</span>
}

export function JobRow({ p, c, today, showCompany = true, active = false }: {
  p: Posting
  c: Company | undefined
  today: string
  showCompany?: boolean
  active?: boolean
}) {
  return (
    <a className={active ? 'row active' : 'row'} href={href.job(p.id)} aria-current={active ? 'page' : undefined}>
      <span className="row-main">
        {showCompany && <span className="row-company">{companyLine(c, p.company)}</span>}
        <span className="row-title">{p.title}</span>
        <span className="row-meta">
          <Deadline p={p} today={today} />
          <span>{p.career}</span>
          {p.headhunter && <span>{copy.job.headhunter}</span>}
        </span>
      </span>
    </a>
  )
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="section-title">
      <h2>{children}</h2>
      {right}
    </div>
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
