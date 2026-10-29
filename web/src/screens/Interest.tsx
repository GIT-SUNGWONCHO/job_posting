import { useState, type FormEvent } from 'react'
import { copy } from '../copy'
import { CompanyRow } from '../components/CompanyRow'
import { Chip, Deadline, Empty, Score, Sep } from '../components/ui'
import { saveApplication, STAGES, type Application, type Stage } from '../lib/applications'
import { addDays, companyLine, dateText, isNewSince, listTitle } from '../lib/format'
import type { Match } from '../lib/matches'
import { href } from '../lib/route'
import { useStars } from '../lib/stars'
import type { Posting, Screen } from '../lib/types'
import { ApplySection } from './ApplySection'

const t = copy.apply
const WEEK = 7

type OnApp = (postingId: string, app: Application | null) => void
type Filter = 'all' | Stage

// 관심(하단 탭): 밑줄 탭 공고 · 회사. 공고는 지원 단계 칩으로 거르고 일정·마감 가까운 순, 단계는 회사 이름 뒤 회색 배지,
// 다가오는 일정은 메타 줄에 파랑으로. 내려간 공고는 맨 아래 흐리게. 회사는 ★한 회사(이번 주 새 공고 많은 순)
export function Interest({ screen, seg, apps, today, matches, onApp }: {
  screen: Screen
  seg: 'jobs' | 'companies'
  apps: Map<string, Application>
  today: string
  matches: Map<string, Match>
  onApp: OnApp
}) {
  const { state: stars } = useStars()
  const starred = stars instanceof Set ? [...stars].filter((k) => k in screen.companies) : []
  const live = [...apps.values()].filter((a) => a.stage !== 'dismissed')
  return (
    <div className="page">
      <div className="list-top"><h1>{t.title}</h1></div>
      <nav className="utabs interest-tabs">
        <a href={href.interest} className={seg === 'jobs' ? 'on' : ''} aria-current={seg === 'jobs' ? 'page' : undefined}>{t.tabJobs(live.length)}</a>
        <a href={href.interestCompanies} className={seg === 'companies' ? 'on' : ''} aria-current={seg === 'companies' ? 'page' : undefined}>{t.tabCompanies(starred.length)}</a>
      </nav>
      {seg === 'jobs'
        ? <InterestJobs screen={screen} apps={apps} today={today} matches={matches} onApp={onApp} />
        : <InterestCompanies screen={screen} keys={starred} />}
    </div>
  )
}

function InterestCompanies({ screen, keys }: { screen: Screen; keys: string[] }) {
  const weekStart = addDays(screen.date, -(WEEK - 1))
  const rows = keys.map((key) => {
    const list = screen.postings.filter((p) => p.company === key && !p.noise)
    return { key, co: screen.companies[key], open: list.length, fresh: list.filter((p) => isNewSince(p, weekStart)).length }
  }).sort((a, b) => b.fresh - a.fresh || b.open - a.open || a.co.name.localeCompare(b.co.name, 'ko'))
  return (
    <>
      <div className="list-head"><span>{t.companySort}</span></div>
      {rows.length === 0 ? <Empty>{t.noCompanies}</Empty> : (
        <div className="rows list">
          {rows.map((r) => <CompanyRow key={r.key} companyKey={r.key} co={r.co} open={r.open} fresh={r.fresh} />)}
        </div>
      )}
    </>
  )
}

function InterestJobs({ screen, apps, today, matches, onApp }: {
  screen: Screen
  apps: Map<string, Application>
  today: string
  matches: Map<string, Match>
  onApp: OnApp
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [adding, setAdding] = useState(false)
  const [showDismissed, setShowDismissed] = useState(false)
  const open = new Map(screen.postings.map((p) => [p.id, p]))
  const all = [...apps.values()]
  const live = all.filter((a) => a.stage !== 'dismissed')
  const dismissed = all.filter((a) => a.stage === 'dismissed')
  const counts = Object.fromEntries(STAGES.map((s) => [s, live.filter((a) => a.stage === s).length])) as Record<Stage, number>
  // 일정·마감 가까운 순: 다가오는 일정, 그다음 마감(관심 단계만), 나머지는 단계로 옮긴 날이 최근인 순. 내려간 공고는 맨 아래
  const soon = (a: Application) => {
    const next = a.nextOn && a.nextOn >= today ? a.nextOn : null
    const dl = a.stage === 'interest' && a.snapshot.deadlineType === 'date' && a.snapshot.deadline && a.snapshot.deadline.slice(0, 10) >= today
      ? a.snapshot.deadline.slice(0, 10) : null
    return [next, dl].filter(Boolean).sort()[0] ?? '9999'
  }
  const isOpen = (a: Application) => open.has(a.postingId) || a.postingId.startsWith('manual:')
  const list = live.filter((a) => filter === 'all' || a.stage === filter).sort((a, b) =>
    Number(!isOpen(a)) - Number(!isOpen(b)) || soon(a).localeCompare(soon(b)) || (b.dates[b.stage] ?? '').localeCompare(a.dates[a.stage] ?? ''))
  return (
    <>
      <div className="chips scroll filter-row">
        <Chip selected={filter === 'all'} onClick={() => setFilter('all')}>{t.all} {live.length}</Chip>
        {STAGES.map((s) => <Chip key={s} selected={filter === s} onClick={() => setFilter(s)}>{t.chip[s]} {counts[s]}</Chip>)}
      </div>
      <div className="list-head">
        <span>{t.sortSoon}</span>
        {!adding && <button type="button" className="text-link small" onClick={() => setAdding(true)}>+ {t.add}</button>}
      </div>
      {adding && <div className="list-more"><AddForm today={today} onApp={onApp} onClose={() => setAdding(false)} /></div>}
      {all.length === 0 ? <Empty>{t.empty}</Empty> : (
        <div className="rows list">
          {list.map((a) => <AppRow key={a.postingId} a={a} posting={open.get(a.postingId)} companies={screen.companies} today={today} match={matches.get(a.postingId)} onApp={onApp} />)}
        </div>
      )}
      {dismissed.length > 0 && (
        <div className="list-more">
          <button type="button" className="text-link" aria-expanded={showDismissed} onClick={() => setShowDismissed(!showDismissed)}>
            {t.long.dismissed} {dismissed.length}
          </button>
          {showDismissed && (
            <div className="rows">
              {dismissed.map((a) => <AppRow key={a.postingId} a={a} posting={open.get(a.postingId)} companies={screen.companies} today={today} match={matches.get(a.postingId)} onApp={onApp} />)}
            </div>
          )}
        </div>
      )}
    </>
  )
}

/** 한 줄: 회사 + 단계 배지 / 목록 제목 / 다가오는 일정(파랑) 또는 마감 | 경력, 오른쪽 점수.
 * 열린 공고는 공고 상세로, 내려갔거나 직접 추가한 공고는 눌러서 그 자리에서 고친다(흐리게) */
function AppRow({ a, posting, companies, today, match, onApp }: {
  a: Application
  posting: Posting | undefined
  companies: Screen['companies']
  today: string
  match?: Match
  onApp: OnApp
}) {
  const [editing, setEditing] = useState(false)
  const s = a.snapshot
  const manual = a.postingId.startsWith('manual:')
  const gone = !posting && !manual
  const next = a.nextOn && a.nextOn >= today ? a.nextOn : null
  const badge = gone ? t.closedBadge : a.stage === 'interest' ? t.beforeApply : t.long[a.stage]
  const meta = next
    ? <span className="next">{[a.nextLabel || t.nextDefault, dateText(next)].join(' ')}</span>
    : posting
      ? <><Deadline p={posting} today={today} /><Sep /><span>{posting.career}</span></>
      : <span>{[a.dates.applied && t.appliedOn(dateText(a.dates.applied)), manual ? t.manual : t.closed, a.stage === 'result' && a.outcome && t.outcomes[a.outcome]].filter(Boolean).join(' · ')}</span>
  const main = (
    <span className="row-main">
      <span className="row-company"><span>{posting ? companyLine(companies[posting.company], posting.company) : s.company}</span><span className={gone || a.stage === 'result' || a.stage === 'dismissed' ? 'badge muted' : a.stage === 'interest' ? 'badge sub' : 'badge'}>{badge}</span></span>
      <span className="row-title">{posting ? listTitle(posting) : s.title}</span>
      <span className="row-meta">{meta}</span>
    </span>
  )
  const score = match && <span className="row-score"><Score value={match.score} /></span>
  if (posting) return <a className="row" href={href.job(a.postingId)}>{main}{score}</a>
  return (
    <div className={gone ? 'app-row gone' : 'app-row'}>
      <button type="button" className="row" aria-expanded={editing} onClick={() => setEditing(!editing)}>{main}{score}</button>
      {editing && (
        <div className="app-edit">
          <ApplySection postingId={a.postingId} company={s.company} app={a} today={today} onChange={onApp} embedded />
          {s.url && <a className="text-link" href={s.url} target="_blank" rel="noreferrer noopener">{t.original} ↗</a>}
        </div>
      )}
    </div>
  )
}

/** 직접 추가: 회사·공고 제목·원문 주소·단계·날짜 */
function AddForm({ today, onApp, onClose }: { today: string; onApp: OnApp; onClose: () => void }) {
  const [company, setCompany] = useState('')
  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [stage, setStage] = useState<Stage>('applied')
  const [date, setDate] = useState(today)
  const [failed, setFailed] = useState(false)
  const [saving, setSaving] = useState(false)

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!company.trim() || !title.trim()) return
    setSaving(true)
    const a: Application = {
      postingId: `manual:${crypto.randomUUID()}`, stage, outcome: null, memo: '', nextOn: null, nextLabel: '',
      dates: { [stage]: date || today },
      snapshot: { company: company.trim(), title: title.trim(), url: url.trim() || null, deadlineType: 'always', deadline: null },
    }
    const ok = await saveApplication(a, today)
    setSaving(false)
    if (!ok) return setFailed(true)
    onApp(a.postingId, a)
    onClose()
  }

  return (
    <form className="form app-add" onSubmit={add}>
      <p className="note">{t.addNote}</p>
      <div className="row2">
        <label className="field"><span>{t.company}</span><input value={company} onChange={(e) => setCompany(e.target.value)} required /></label>
        <label className="field"><span>{t.stage}</span>
          <select value={stage} onChange={(e) => setStage(e.target.value as Stage)}>
            {STAGES.map((s) => <option key={s} value={s}>{t.long[s]}</option>)}
          </select>
        </label>
      </div>
      <label className="field"><span>{t.postingTitle}</span><input value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
      <div className="row2">
        <label className="field"><span>{t.url}</span><input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></label>
        <label className="field"><span>{t.date}</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
      </div>
      <div className="feedback-actions">
        {failed && <span className="note urgent">{t.failed}</span>}
        <button type="button" className="btn" onClick={onClose}>{t.close}</button>
        <button type="submit" className="btn primary" disabled={saving || !company.trim() || !title.trim()}>{t.addSave}</button>
      </div>
    </form>
  )
}
