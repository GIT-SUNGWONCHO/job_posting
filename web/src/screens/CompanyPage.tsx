import { useEffect, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { YearBars } from '../components/charts'
import { JobRow, SectionTitle } from '../components/ui'
import { dartUrl, dateText, growth, manwon, money, pointChange, yearMonth } from '../lib/format'
import { loadCompanies } from '../lib/load'
import { goBack, href } from '../lib/route'
import type { CompaniesFile, CompanyBasics, DartBasics, Filters, PastPosting, Screen } from '../lib/types'

const t = copy.company
const PAST_SHOWN = 5
const OPEN_SHOWN = 10

// 회사 화면(와이어프레임 M4의 기본정보): 회사 개요(DART 공시 사실만) + 채용(열린 공고, 지난 공고).
// 심층분석 모듈은 아직 없다. 숫자마다 출처 줄(종류 · 문서 · 날짜 ↗)을 단다(docs/content-rules.md)
export function CompanyPage({ screen, companyKey, today, filters, panel = false }: {
  screen: Screen
  companyKey: string
  today: string
  filters: Filters
  panel?: boolean
}) {
  const c = screen.companies[companyKey]
  const open = screen.postings.filter((p) => p.company === companyKey && !p.noise)
  const [file, setFile] = useState<CompaniesFile | null | 'failed'>(null)
  const [allOpen, setAllOpen] = useState(false)
  useEffect(() => {
    let alive = true
    loadCompanies().then((f) => alive && setFile(f), () => alive && setFile('failed'))
    return () => {
      alive = false
    }
  }, [])
  const basics: CompanyBasics | undefined = file && file !== 'failed' ? file.companies[companyKey] : undefined
  const dart = basics?.dart
  const listed = dart && 'market' in dart && dart.market ? t.market(dart.market) : null

  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && (
        <div className="topbar">
          <button type="button" className="icon-btn" aria-label={copy.job.back} onClick={() => goBack(href.companies)}>‹</button>
        </div>
      )}
      <header className="page-head company-head">
        <span className="logo" aria-hidden="true">{(c?.name ?? companyKey).slice(0, 1)}</span>
        <div>
          <h1>{c?.name ?? companyKey}</h1>
          <div className="page-sub">{[c?.group && `${c.group} 계열`, c?.type, listed].filter(Boolean).join(' · ')}</div>
        </div>
      </header>

      <section className="section">
        <SectionTitle right={dart && 'fetched' in dart ? <span className="count">{t.updated(dateText(dart.fetched))}</span> : undefined}>
          {t.overview}
        </SectionTitle>
        {file === null && <p className="note">{t.loading}</p>}
        {file === 'failed' && <p className="note">{t.loadFailed}</p>}
        {file && file !== 'failed' && <Overview basics={basics} />}
      </section>

      <section className="section">
        <SectionTitle right={<span className="count">{t.daily}</span>}>{t.hiring}</SectionTitle>
        <div className="sub-head">{copy.jobs.openCount(open.length)}</div>
        <div className="rows">
          {(allOpen ? open : open.slice(0, OPEN_SHOWN)).map((p) => <JobRow key={p.id} p={p} c={c} today={today} showCompany={false} />)}
        </div>
        {!allOpen && open.length > OPEN_SHOWN && (
          <button type="button" className="text-link" onClick={() => setAllOpen(true)}>{copy.jobs.more(open.length - OPEN_SHOWN)}</button>
        )}
        {file && file !== 'failed' && <Past past={basics?.past ?? []} byJob={basics?.pastByJob ?? {}} since={file.since}
          jobs={filters.job_types ?? []} />}
      </section>
    </div>
  )
}

function Source({ text, date, rceptNo }: { text: string; date?: string | null; rceptNo?: string | null }) {
  const label = [text, date].filter(Boolean).join(' · ')
  return rceptNo
    ? <a className="source" href={dartUrl(rceptNo)} target="_blank" rel="noreferrer noopener">{label} ↗</a>
    : <span className="source">{label}</span>
}

function Overview({ basics }: { basics: CompanyBasics | undefined }) {
  const dart = basics?.dart
  if (!dart) return <p className="note">{t.notChecked}</p>
  if ('none' in dart) return <p className="not-found">{t.notFound(dart.none === 'ambiguous' ? t.ambiguous : t.noDart)}</p>
  if ('pending' in dart) return <p className="note">{t.pending(dart.corpName)}</p>
  return <DartOverview d={dart} />
}

function DartOverview({ d }: { d: DartBasics }) {
  const fin = d.finance
  const years = fin?.years ?? []
  const cur = years[years.length - 1]
  const prev = years[years.length - 2]
  const hasRevenue = cur?.revenue !== null && cur?.revenue !== undefined
  const chartField = hasRevenue ? 'revenue' : 'operating'
  // 영업수익으로 적는 회사는 그 이름 그대로(매출로 바꿔 부르지 않는다)
  const revenueLabel = fin?.revenueName === '영업수익' ? t.operatingRevenue : t.revenue
  const margin = (y: typeof cur | undefined) =>
    y && y.revenue && y.operating !== null && y.operating !== undefined ? (y.operating / y.revenue) * 100 : null
  const emp = d.employees
  const info: [string, ReactNode][] = []
  if (d.ceo) info.push([t.ceo, d.ceo])
  if (d.founded) info.push([t.founded, dateText(d.founded, true)])
  if (d.homepage) {
    info.push([t.homepage, <a key="hp" className="text-link inline" href={d.homepage} target="_blank" rel="noreferrer noopener">
      {d.homepage.replace(/^https?:\/\//, '').replace(/\/$/, '')} ↗</a>])
  }

  return (
    <div className="overview">
      {fin && cur && (
        <>
          {/* 금융사처럼 매출액 줄이 없으면 영업이익·순이익만(다른 계정으로 바꿔 넣지 않는다) */}
          {hasRevenue ? (
            <div className="tiles three">
              <Tile label={t.yearOf(revenueLabel, cur.year)} value={cur.revenue} delta={growth(cur.revenue, prev?.revenue)} fmt={money} />
              <Tile label={t.operating} value={cur.operating} delta={growth(cur.operating, prev?.operating)} fmt={money} />
              <Tile label={t.margin} value={margin(cur)} delta={pointChange(margin(cur), margin(prev))} fmt={(v) => `${v.toFixed(1)}%`} />
            </div>
          ) : (
            <div className="tiles">
              <Tile label={t.yearOf(t.operating, cur.year)} value={cur.operating} delta={growth(cur.operating, prev?.operating)} fmt={money} />
              <Tile label={t.net} value={cur.net} delta={growth(cur.net, prev?.net)} fmt={money} />
            </div>
          )}
          {years.filter((y) => y[chartField] !== null && y[chartField] !== undefined).length > 1 && (
            <>
              <h3 className="chart-title">{t.byYear(hasRevenue ? revenueLabel : t.operating)}</h3>
              <YearBars data={years.map((y) => ({ year: y.year, value: y[chartField] }))}
                label={t.byYear(hasRevenue ? revenueLabel : t.operating)} format={money} />
            </>
          )}
          {!hasRevenue && <p className="note small">{t.noRevenue}</p>}
          <Source text={t.sourceFinance(fin.year, fin.basis)} date={yearMonth(fin.rceptNo)} rceptNo={fin.rceptNo} />
        </>
      )}
      {(emp || info.length > 0) && (
        <dl className="kv">
          {emp && <div><dt>{t.employees}</dt><dd>{t.people(emp.count)}</dd></div>}
          {emp && (emp.tenure !== null || emp.salary !== null) && (
            <div><dt>{t.tenureSalary}</dt><dd>{t.tenureSalaryValue(emp.tenure !== null ? emp.tenure.toFixed(1) : null,
              emp.salary !== null ? manwon(emp.salary) : null)}</dd></div>
          )}
          {info.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      )}
      {emp && <Source text={t.sourceEmployees} date={yearMonth(emp.rceptNo)} rceptNo={emp.rceptNo} />}
      {!emp && info.length > 0 && <Source text={t.sourceCompany} />}

      <h3 className="sub-head">{t.disclosures}</h3>
      {d.disclosures.length === 0 ? <p className="note">{t.noDisclosures}</p> : (
        <div className="disclosures">
          {d.disclosures.map((x) => (
            <a key={x.rceptNo ?? x.title} className="disclosure" href={x.rceptNo ? dartUrl(x.rceptNo) : undefined}
              target="_blank" rel="noreferrer noopener">
              <span className="disclosure-date">{yearMonth(x.date)}</span>
              <span>{x.title}</span>
            </a>
          ))}
          <Source text={t.sourceDisclosures} />
        </div>
      )}
      {!fin && <p className="not-found">{t.notFound(t.noFinance)}</p>}
    </div>
  )
}

function Tile({ label, value, delta, fmt }: {
  label: string
  value: number | null | undefined
  delta: string | null
  fmt: (v: number) => string
}) {
  return (
    <div className="tile">
      <span className="tile-label">{label}</span>
      <b className="tile-value">{value === null || value === undefined ? '-' : fmt(value)}</b>
      {delta && <span className="tile-delta">{t.vsLastYear} {delta}</span>}
    </div>
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
    <div className="past">
      <div className="sub-head">
        <span>{t.pastTitle}</span>
        {total > 0 && <span className="count">{jobs.length && !all ? t.pastMine(mineTotal, total) : t.pastAll(total)}</span>}
      </div>
      {list.length === 0 ? <p className="note">{total === 0 ? t.noPast : t.noPastMine}</p> : (
        <div className="past-rows">
          {shown.map((p) => (
            <div key={p.title + p.firstSeen + p.closedOn} className="past-row">
              <span className="past-date">{t.closedOn(dateText(p.closedOn))}</span>
              <span>{p.title}</span>
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
      <p className="note small">{t.pastNote(dateText(since, true))}</p>
    </div>
  )
}
