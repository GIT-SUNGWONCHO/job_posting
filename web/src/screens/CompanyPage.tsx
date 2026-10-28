import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { SourceSheet, type SourceItem } from '../components/SourceSheet'
import { BACK_ICON, JobRow, RIGHT_ICON, SectionTitle, Sep, STAR_ICON } from '../components/ui'
import { passes } from '../lib/filter'
import { dartUrl, dateText, listTitle, money, yearMonth } from '../lib/format'
import { loadCompanies } from '../lib/load'
import { loadNote, type Note } from '../lib/notes'
import { goBack, href } from '../lib/route'
import { isStarred, useStars } from '../lib/stars'
import type { CompaniesFile, CompanyBasics, Competitors, DartBasics, Filters, PastPosting, Screen } from '../lib/types'

const t = copy.company
const PAST_SHOWN = 5
const OPEN_SHOWN = 10


// 회사 화면: 이름 · 기업 구분 | 그룹 | 상장 → 기본정보(DART) → 실적(매출 · 영업이익 · 이익률 3년) → 내 리서치 노트
// → 같은 업종 회사 → 열린 공고 · 지난 공고. 출처는 섹션 제목 오른쪽 "출처"를 눌러 시트로(docs/content-rules.md)
export function CompanyPage({ screen, companyKey, today, filters, panel = false }: {
  screen: Screen
  companyKey: string
  today: string
  filters: Filters
  panel?: boolean
}) {
  const c = screen.companies[companyKey]
  // 필터를 통과한 공고를 먼저, 나머지는 그 뒤에
  const all = screen.postings.filter((p) => p.company === companyKey && !p.noise)
  const passed = all.filter((p) => passes(p, c, filters))
  const open = [...passed, ...all.filter((p) => !passed.includes(p))]
  const [file, setFile] = useState<CompaniesFile | null | 'failed'>(null)
  const [attempt, setAttempt] = useState(0)
  const [allOpen, setAllOpen] = useState(false)
  const [sheet, setSheet] = useState<{ title: string; items: SourceItem[] } | null>(null)
  useEffect(() => {
    let alive = true
    loadCompanies().then((f) => alive && setFile(f), () => alive && setFile('failed'))
    return () => {
      alive = false
    }
  }, [attempt])
  const basics: CompanyBasics | undefined = file && file !== 'failed' ? file.companies[companyKey] : undefined
  const dart = basics?.dart
  const d = dart && 'fetched' in dart ? dart : undefined
  const listed = d?.market ? t.market(d.market) : null
  const stars = useStars()
  const on = isStarred(stars.state, companyKey)
  const name = c?.name ?? companyKey
  const meta = [c?.type, c?.group && `${c.group} 계열`, listed].filter(Boolean) as string[]
  const srcBtn = (title: string, items: SourceItem[]) => items.length > 0 && (
    <button type="button" className="src-btn" onClick={() => setSheet({ title, items })}>{copy.common.source}</button>
  )

  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      <div className="topbar">
        {!panel && <button type="button" className="icon-btn" aria-label={copy.common.back} onClick={() => goBack(href.companies)}>{BACK_ICON}</button>}
        {stars.state !== undefined && stars.state !== 'failed' && (
          <button type="button" className={on ? 'star-btn on top' : 'star-btn top'} aria-pressed={on}
            aria-label={stars.state === 'missing' ? t.starsMissing : on ? t.unstar : t.star}
            title={stars.state === 'missing' ? t.starsMissing : undefined}
            disabled={stars.state === 'missing'} onClick={() => stars.toggle(companyKey)}>{STAR_ICON}</button>
        )}
      </div>
      <header className="detail-head company-intro">
        <h1>{name}</h1>
        {meta.length > 0 && <div className="intro-meta">{meta.map((m, i) => <Fragment key={m}>{i > 0 && <Sep />}<span>{m}</span></Fragment>)}</div>}
        {stars.state === 'missing' && <p className="note">{t.starsMissing}</p>}
      </header>

      {file === null && <section className="section"><p className="note">{t.loading}</p></section>}
      {file === 'failed' && (
        <section className="section">
          <div className="load-failed">
            <p className="note">{t.loadFailed}</p>
            <button type="button" className="text-link" onClick={() => { setFile(null); setAttempt((a) => a + 1) }}>{copy.load.retry}</button>
          </div>
        </section>
      )}
      {file && file !== 'failed' && (
        <>
          <section className="section">
            <SectionTitle right={d && srcBtn(t.basicsSource, basicsSources(d))}>{t.basics}</SectionTitle>
            {d ? <Basics d={d} /> : <NotFound basics={basics} isPublic={c?.type === '공기업·공공기관'} />}
          </section>
          {d?.finance && d.finance.years.length > 0 && (
            <section className="section">
              <SectionTitle right={srcBtn(t.financeSource, [{
                title: t.sourceFinance(d.finance.year, d.finance.basis), detail: t.financeUse(d.finance.revenueName === '영업수익'),
                url: d.finance.rceptNo && dartUrl(d.finance.rceptNo),
              }])}>{t.finance}</SectionTitle>
              <FinanceTable fin={d.finance} />
            </section>
          )}
          <NoteSection companyKey={companyKey} />
          <Peers data={basics?.research?.competitors} onSource={(items) => setSheet({ title: t.peersSource, items })} />
        </>
      )}

      <section className="section open-sec">
        <SectionTitle count={open.length}>{t.open}</SectionTitle>
        {open.length === 0 ? <p className="note">{copy.jobs.noOpen}</p> : (
          <div className="rows">
            {(allOpen ? open : open.slice(0, OPEN_SHOWN)).map((p) => <JobRow key={p.id} p={p} c={c} today={today} showCompany={false} />)}
          </div>
        )}
        {!allOpen && open.length > OPEN_SHOWN && (
          <button type="button" className="btn block more" onClick={() => setAllOpen(true)}>{copy.jobs.more(open.length - OPEN_SHOWN)}</button>
        )}
      </section>
      {file && file !== 'failed' && <Past past={basics?.past ?? []} byJob={basics?.pastByJob ?? {}} since={file.since} jobs={filters.job_types ?? []} />}

      {sheet && <SourceSheet title={sheet.title} items={sheet.items} onClose={() => setSheet(null)} />}
    </div>
  )
}

/** 내 리서치 노트: 있으면 섹션 줄(누르면 노트 화면의 그 섹션으로), 없으면 무엇인지 설명 */
function NoteSection({ companyKey }: { companyKey: string }) {
  const [note, setNote] = useState<{ key: string; note: Note | null } | null>(null)
  useEffect(() => {
    let alive = true
    loadNote(companyKey).then((n) => alive && setNote({ key: companyKey, note: n }), () => alive && setNote({ key: companyKey, note: null }))
    return () => {
      alive = false
    }
  }, [companyKey])
  const n = note?.key === companyKey ? note.note : undefined
  return (
    <section className="section">
      <SectionTitle info={t.noteHelp} right={n && <span className="count">{t.noteUpdated(dateText(n.updated))}</span>}>{t.note}</SectionTitle>
      {n === undefined ? <p className="note">{t.loading}</p> : n ? (
        <div className="note-rows">
          {n.sections.map((sec, i) => <a key={sec.title} href={href.note(companyKey, i)}>{sec.title}{RIGHT_ICON}</a>)}
        </div>
      ) : (
        <div className="note-empty">
          <span>{t.noteHelp}</span>
          <span className="muted">{t.noteNow}</span>
        </div>
      )}
    </section>
  )
}

function basicsSources(d: DartBasics): SourceItem[] {
  const out: SourceItem[] = [{ title: t.sourceCompany, detail: t.companyUse }]
  if (d.employees) {
    out.push({
      title: t.sourceEmployees, detail: [t.employeesUse, yearMonth(d.employees.rceptNo) && t.received(yearMonth(d.employees.rceptNo)!)].filter(Boolean).join(' · '),
      url: d.employees.rceptNo && dartUrl(d.employees.rceptNo),
    })
  }
  return out
}

/** DART와 잇지 못했거나 아직 받지 않은 회사 */
function NotFound({ basics, isPublic }: { basics: CompanyBasics | undefined; isPublic: boolean }) {
  const dart = basics?.dart
  if (!dart) return <p className="note">{t.notChecked}</p>
  if ('pending' in dart) return <p className="note">{t.pending(dart.corpName)}</p>
  if ('none' in dart) {
    // 공공기관은 대부분 DART가 아니라 알리오(공공기관 경영정보 공개)에 공시한다
    const topic = dart.none === 'ambiguous' || dart.none === 'mixed' ? t.ambiguous : isPublic ? t.noDartPublic : t.noDart
    return <p className="not-found">{t.notFound(topic)}</p>
  }
  return null
}

/** 기본정보: 법인명 · 대표 · 설립 · 임직원 · 평균 근속 · 1인 평균 급여 · 홈페이지 */
function Basics({ d }: { d: DartBasics }) {
  const emp = d.employees
  const rows: [string, ReactNode][] = []
  const legal = d.legalName || d.corpName
  if (legal) rows.push([t.legalName, legal])
  if (d.ceo || d.founded) rows.push([t.ceoFounded, [d.ceo, d.founded && dateText(d.founded, true).slice(0, 7)].filter(Boolean).join(' · ')])
  if (emp) {
    rows.push([t.employees, t.people(emp.count)])
    if (emp.tenure !== null) rows.push([t.tenure, t.years(emp.tenure.toFixed(1))])
    if (emp.salary !== null) rows.push([t.salary, money(emp.salary)])
  }
  if (d.homepage) {
    rows.push([t.homepage, <a key="hp" className="ext" href={d.homepage} target="_blank" rel="noreferrer noopener">
      {d.homepage.replace(/^https?:\/\//, '').replace(/\/$/, '')} ↗</a>])
  }
  return (
    <>
      <div className="kv2 wide">{rows.map(([k, v]) => <Fragment key={k}><span className="k">{k}</span><span className="v">{v}</span></Fragment>)}</div>
      {!emp && <p className="not-found">{t.notFound(t.noEmployees)}</p>}
    </>
  )
}

/** 실적: 연도별 매출 막대(올해만 파랑)와 같은 열에 영업이익 · 이익률. 매출 줄이 없는 회사(은행 등)는 영업이익만 */
function FinanceTable({ fin }: { fin: NonNullable<DartBasics['finance']> }) {
  const years = fin.years.slice(-3)
  const hasRevenue = years.some((y) => y.revenue !== null && y.revenue !== undefined)
  const max = Math.max(...years.map((y) => Math.abs((hasRevenue ? y.revenue : y.operating) ?? 0)), 1)
  const last = years.length - 1
  const revenueLabel = fin.revenueName === '영업수익' ? t.operatingRevenue : t.revenue
  const margin = (y: (typeof years)[number]) =>
    y.revenue && y.operating !== null && y.operating !== undefined ? `${((y.operating / y.revenue) * 100).toFixed(1)}%` : '-'
  const cols = { gridTemplateColumns: `64px repeat(${years.length}, minmax(0, 1fr))` }
  const barValue = (y: (typeof years)[number]) => (hasRevenue ? y.revenue : y.operating)
  return (
    <div className="fin" role="table" aria-label={t.finance}>
      <div className="fin-bars" style={cols}>
        <span className="fin-k">{hasRevenue ? revenueLabel : t.operating}</span>
        {years.map((y, i) => {
          const v = barValue(y)
          return (
            <span key={y.year} className={i === last ? 'fin-bar on' : 'fin-bar'}>
              <b>{v === null || v === undefined ? '-' : money(v)}</b>
              <i style={{ height: `${Math.max(((Math.abs(v ?? 0)) / max) * 100, 2)}px` }} />
            </span>
          )
        })}
      </div>
      <div className="fin-years" style={cols}><span />{years.map((y, i) => <span key={y.year} className={i === last ? 'on' : ''}>{y.year}</span>)}</div>
      {hasRevenue && (
        <div className="fin-rows" style={cols}>
          <span className="fin-k">{t.operating}</span>
          {years.map((y) => <span key={y.year}>{y.operating === null || y.operating === undefined ? '-' : money(y.operating)}</span>)}
          <span className="fin-k sub">{t.marginShort}</span>
          {years.map((y) => <span key={y.year} className="sub">{margin(y)}</span>)}
        </div>
      )}
    </div>
  )
}

/** 같은 업종 회사: 이 회사(굵게, "이 회사")와 같은 DART 업종에서 매출이 큰 곳. 화면에 있는 회사는 회사 화면으로 */
function Peers({ data, onSource }: { data: Competitors | undefined; onSource: (items: SourceItem[]) => void }) {
  const others = data?.rows.filter((r) => !r.self) ?? []
  if (!data || others.length === 0) return null
  const h = t.competitorsHead
  const items: SourceItem[] = [{ title: t.peersRule, detail: t.sourceCompetitors(data.industry) },
    ...data.rows.filter((r) => r.rceptNo).map((r) => ({
      title: r.name, detail: [r.year, r.basis, r.revenueName === '영업수익' && t.operatingRevenue].filter(Boolean).join(' · '),
      url: dartUrl(r.rceptNo!),
    }))]
  return (
    <section className="section">
      <SectionTitle right={<button type="button" className="src-btn" onClick={() => onSource(items)}>{copy.common.source}</button>}>{t.peers}</SectionTitle>
      <div className="peers" role="table">
        <span /><span className="th">{h.revenue}</span><span className="th">{h.margin}</span>
        {data.rows.map((r) => (
          <Fragment key={r.name + (r.self ? '*' : '')}>
            <span className={r.self ? 'name self' : 'name'}>
              {r.key && !r.self ? <a href={href.company(r.key)}>{r.name}</a> : r.name}
              {r.self && <span className="badge">{t.self}</span>}
            </span>
            <span>{r.revenue === null ? '-' : money(r.revenue)}</span>
            <span>{r.margin === null ? '-' : `${r.margin.toFixed(1)}%`}</span>
          </Fragment>
        ))}
      </div>
    </section>
  )
}

/** 지난 공고: 내 직무(개인 필터)만 먼저, 다른 직무는 눌러서. 분류 전 공고는 내 직무에 넣는다(필터와 같게) */
function Past({ past, byJob, since, jobs }: { past: PastPosting[]; byJob: Record<string, number>; since: string; jobs: string[] }) {
  const [all, setAll] = useState(false)
  const [more, setMore] = useState(false)
  const isMine = (job: string | null) => !jobs.length || !job || job === 'none' || jobs.includes(job)
  const mine = past.filter((p) => isMine(p.jobType))
  const total = Object.values(byJob).reduce((a, b) => a + b, 0)
  const mineTotal = Object.entries(byJob).filter(([j]) => isMine(j)).reduce((a, [, n]) => a + n, 0)
  const list = all ? past : mine
  const shown = more ? list : list.slice(0, PAST_SHOWN)
  return (
    <section className="section past-sec">
      <SectionTitle count={jobs.length && !all ? mineTotal : total} info={t.pastNote(dateText(since, true))}>{t.pastTitle}</SectionTitle>
      {list.length === 0 ? <p className="note">{total === 0 ? t.noPast : t.noPastMine}</p> : (
        <div className="past-rows">
          {shown.map((p) => (
            <div key={p.id} className="past-row">
              <span className="past-title">{listTitle(p)}</span>
              <span className="badge muted">{t.closedOn(dateText(p.closedOn))}</span>
            </div>
          ))}
        </div>
      )}
      <div className="past-actions">
        {list.length > PAST_SHOWN && !more && (
          <button type="button" className="text-link" onClick={() => setMore(true)}>{copy.apply.more(list.length - PAST_SHOWN)}</button>
        )}
        {jobs.length > 0 && !all && mine.length < past.length && (
          <button type="button" className="text-link" onClick={() => setAll(true)}>{t.showAllPast}</button>
        )}
      </div>
    </section>
  )
}
