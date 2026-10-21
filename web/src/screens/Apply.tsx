import { useState, type FormEvent } from 'react'
import { copy } from '../copy'
import { Deadline, Empty, SectionTitle } from '../components/ui'
import { saveApplication, STAGES, upcoming, type Application, type Stage } from '../lib/applications'
import { dateText } from '../lib/format'
import { href } from '../lib/route'
import type { Posting, Screen } from '../lib/types'
import { ApplySection } from './ApplySection'

const t = copy.apply
const SHOW = 3

type OnApp = (postingId: string, app: Application | null) => void

// 지원 현황(와이어프레임 M6): 단계별 숫자, 다가오는 일정, 단계별 목록. 관심 없음은 맨 아래 접어 둔다.
// 수집되지 않았거나 마감된 공고는 직접 추가하고, 목록에서 눌러 그 자리에서 고친다
export function Apply({ screen, apps, today, onApp }: {
  screen: Screen
  apps: Map<string, Application>
  today: string
  onApp: OnApp
}) {
  const [counts, groups] = group(apps)
  const [adding, setAdding] = useState(false)
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
        {adding
          ? <AddForm today={today} onApp={onApp} onClose={() => setAdding(false)} />
          : <button type="button" className="btn" onClick={() => setAdding(true)}>+ {t.add}</button>}
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
            <StageList key={s} stage={s} list={groups[s]} open={open} today={today} onApp={onApp} />
          ))}
          {groups.dismissed.length > 0 && (
            <section className="section">
              <details>
                <summary className="section-title"><h2>{t.long.dismissed} <span className="count">{groups.dismissed.length}</span></h2></summary>
                <p className="note">{t.dismissedNote}</p>
                <div className="rows">
                  {groups.dismissed.map((a) => <AppRow key={a.postingId} a={a} posting={open.get(a.postingId)} today={today} onApp={onApp} />)}
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

function StageList({ stage, list, open, today, onApp }: {
  stage: Stage
  list: Application[]
  open: Map<string, Posting>
  today: string
  onApp: OnApp
}) {
  const [all, setAll] = useState(false)
  const shown = all ? list : list.slice(0, SHOW)
  return (
    <section className="section" id={`stage-${stage}`}>
      <SectionTitle right={<span className="count">{list.length}</span>}>{t.long[stage]}</SectionTitle>
      <div className="rows">
        {shown.map((a) => <AppRow key={a.postingId} a={a} posting={open.get(a.postingId)} today={today} onApp={onApp} />)}
      </div>
      {list.length > SHOW && !all && (
        <button type="button" className="text-link" onClick={() => setAll(true)}>{t.more(list.length - SHOW)}</button>
      )}
    </section>
  )
}

/** 한 줄: 회사 / 공고 제목 / 단계에 맞는 보조 정보(관심: 마감, 지원 이후: 지원한 날·결과·메모).
 * 열린 공고는 공고 상세로, 마감되거나 직접 추가한 공고는 눌러서 그 자리에서 고친다 */
function AppRow({ a, posting, today, onApp }: { a: Application; posting: Posting | undefined; today: string; onApp: OnApp }) {
  const [editing, setEditing] = useState(false)
  const s = a.snapshot
  const manual = a.postingId.startsWith('manual:')
  const meta: string[] = []
  if (a.stage !== 'interest' && a.dates.applied) meta.push(t.appliedOn(dateText(a.dates.applied)))
  if (a.stage === 'result' && a.outcome) meta.push(t.outcomes[a.outcome])
  if (a.nextOn && a.nextOn >= today) meta.push(`${t.nextOf('', a.nextLabel).trim()} ${dateText(a.nextOn)}`)
  if (a.memo) meta.push(t.hasMemo)
  if (!posting) meta.push(manual ? t.manual : t.closed)
  const main = (
    <span className="row-main">
      <span className="row-company">{s.company}</span>
      <span className="row-title">{s.title}</span>
      <span className="row-meta">
        {a.stage === 'interest' && posting && <Deadline p={posting} today={today} />}
        {meta.map((m) => <span key={m}>{m}</span>)}
      </span>
    </span>
  )
  if (posting) return <a className="row" href={href.job(a.postingId)}>{main}</a>
  return (
    <div className="app-row">
      <button type="button" className="row" aria-expanded={editing} onClick={() => setEditing(!editing)}>{main}</button>
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
