import { copy } from '../copy'
import { href } from '../lib/route'
import { isStarred, useStars } from '../lib/stars'
import type { Company } from '../lib/types'
import { Sep, STAR_ICON } from './ui'

/** 회사 한 줄: 이름 / 기업 구분 · 그룹 계열 / 열린 공고 N | 이번 주 새 공고 N(파랑), 오른쪽 ★ */
export function CompanyRow({ companyKey, co, open, fresh }: { companyKey: string; co: Company; open: number; fresh: number }) {
  const { state: stars, toggle } = useStars()
  const on = isStarred(stars, companyKey)
  return (
    <div className="row company-row">
      <a className="row-main" href={href.company(companyKey)}>
        <span className="row-title">{co.name}</span>
        <span className="row-company"><span>{[co.type, co.group && `${co.group} 계열`].filter(Boolean).join(' · ')}</span></span>
        <span className="row-meta">
          <span>{open > 0 ? copy.jobs.openCount(open) : copy.jobs.noOpen}</span>
          {fresh > 0 && <><Sep /><span className="fresh">{copy.jobs.freshCount(fresh)}</span></>}
        </span>
      </a>
      {stars instanceof Set && (
        <button type="button" className={on ? 'star-btn on' : 'star-btn'} aria-pressed={on}
          aria-label={copy.company.starLabel(co.name)} onClick={() => toggle(companyKey)}>{STAR_ICON}</button>
      )}
    </div>
  )
}
