import { useEffect, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { YearBars } from '../components/charts'
import { JobRow, SectionTitle } from '../components/ui'
import { passes } from '../lib/filter'
import { dartUrl, dateText, growth, money, pointChange, yearMonth } from '../lib/format'
import { loadCompanies } from '../lib/load'
import { goBack, href } from '../lib/route'
import { isStarred, useStars } from '../lib/stars'
import type { CompaniesFile, CompanyBasics, Competitors, DartBasics, Filters, PastPosting, Screen, ToolsFound } from '../lib/types'

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
  // 필터를 통과한 공고(회사 목록의 "열린 공고" 수와 같은 것)를 먼저, 나머지는 그 뒤에
  const all = screen.postings.filter((p) => p.company === companyKey && !p.noise)
  const passed = all.filter((p) => passes(p, c, filters))
  const open = [...passed, ...all.filter((p) => !passed.includes(p))]
  const [file, setFile] = useState<CompaniesFile | null | 'failed'>(null)
  const [attempt, setAttempt] = useState(0)
  const [allOpen, setAllOpen] = useState(false)
  useEffect(() => {
    let alive = true
    loadCompanies().then((f) => alive && setFile(f), () => alive && setFile('failed'))
    return () => {
      alive = false
    }
  }, [attempt])
  const basics: CompanyBasics | undefined = file && file !== 'failed' ? file.companies[companyKey] : undefined
  const dart = basics?.dart
  const listed = dart && 'market' in dart && dart.market ? t.market(dart.market) : null
  const stars = useStars()
  const on = isStarred(stars.state, companyKey)

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
          {stars.state === 'missing' && <p className="note small">{t.starsMissing}</p>}
        </div>
        {stars.state !== undefined && stars.state !== 'failed' && (
          <button type="button" className={on ? 'star-btn on' : 'star-btn'} aria-pressed={on}
            aria-label={stars.state === 'missing' ? t.starsMissing : on ? t.unstar : t.star}
            title={stars.state === 'missing' ? t.starsMissing : undefined}
            disabled={stars.state === 'missing'} onClick={() => stars.toggle(companyKey)}>{on ? '★' : '☆'}</button>
        )}
      </header>

      <section className="section">
        <SectionTitle right={dart && 'fetched' in dart ? <span className="count">{t.updated(dateText(dart.fetched))}</span> : undefined}>
          {t.overview}
        </SectionTitle>
        {file === null && <p className="note">{t.loading}</p>}
        {file === 'failed' && (
          <div className="load-failed">
            <p className="note">{t.loadFailed}</p>
            <button type="button" className="text-link" onClick={() => { setFile(null); setAttempt((a) => a + 1) }}>{copy.load.retry}</button>
          </div>
        )}
        {file && file !== 'failed' && <Overview basics={basics} isPublic={c?.type === '공기업·공공기관'} />}
      </section>

      <section className="section">
        <SectionTitle right={<span className="count">{t.daily}</span>}>{t.hiring}</SectionTitle>
        <div className="sub-head">
          <span>{open.length > 0 ? copy.jobs.openCount(open.length) : copy.jobs.noOpen}</span>
          {passed.length < open.length && <span className="count">{t.openPassed(passed.length)}</span>}
        </div>
        <div className="rows">
          {(allOpen ? open : open.slice(0, OPEN_SHOWN)).map((p) => <JobRow key={p.id} p={p} c={c} today={today} showCompany={false} />)}
        </div>
        {!allOpen && open.length > OPEN_SHOWN && (
          <button type="button" className="text-link" onClick={() => setAllOpen(true)}>{copy.jobs.more(open.length - OPEN_SHOWN)}</button>
        )}
        {file && file !== 'failed' && <Past past={basics?.past ?? []} byJob={basics?.pastByJob ?? {}} since={file.since}
          jobs={filters.job_types ?? []} />}
      </section>

      {file && file !== 'failed' && (
        <section className="section deep">
          <h2 className="group-title">{t.deep}</h2>
          <CompetitorsView data={basics?.research?.competitors} hasDart={!!dart && 'corpCode' in dart} />
          <ToolsView data={basics?.research?.tools} since={file.since} />
        </section>
      )}
    </div>
  )
}

function Source({ text, date, rceptNo }: { text: string; date?: string | null; rceptNo?: string | null }) {
  const label = [text, date].filter(Boolean).join(' · ')
  return rceptNo
    ? <a className="source" href={dartUrl(rceptNo)} target="_blank" rel="noreferrer noopener">{label} ↗</a>
    : <span className="source">{label}</span>
}

function Overview({ basics, isPublic }: { basics: CompanyBasics | undefined; isPublic: boolean }) {
  const dart = basics?.dart
  if (!dart) return <p className="note">{t.notChecked}</p>
  if ('none' in dart) {
    // 공공기관은 대부분 DART가 아니라 알리오(공공기관 경영정보 공개)에 공시한다
    const topic = dart.none === 'ambiguous' || dart.none === 'mixed' ? t.ambiguous : isPublic ? t.noDartPublic : t.noDart
    return <p className="not-found">{t.notFound(topic)}</p>
  }
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
  // 전년 중간에 세운 회사(분할 신설 등)는 전년이 몇 달치라 전년 대비를 보여주지 않는다
  const partialPrev = !!(prev && d.founded && d.founded > `${prev.year}-01-01`)
  const vs = (delta: string | null) => (partialPrev ? null : delta)
  const emp = d.employees
  const info: [string, ReactNode][] = []
  const legal = d.legalName || d.corpName
  if (legal) info.push([t.legalName, legal])
  if (d.ceo) info.push([t.ceo, d.ceo])
  if (d.founded) info.push([t.founded, dateText(d.founded, true)])
  if (d.homepage) {
    info.push([t.homepage, <a key="hp" className="plain-link" href={d.homepage} target="_blank" rel="noreferrer noopener">
      {d.homepage.replace(/^https?:\/\//, '').replace(/\/$/, '')} ↗</a>])
  }

  return (
    <div className="overview">
      {fin && cur && (
        <>
          {/* 금융사처럼 매출액 줄이 없으면 영업이익·순이익만(다른 계정으로 바꿔 넣지 않는다) */}
          {hasRevenue ? (
            <div className="tiles three">
              <Tile label={t.yearOf(revenueLabel, cur.year)} value={cur.revenue} delta={vs(growth(cur.revenue, prev?.revenue))} fmt={money} />
              <Tile label={t.operating} value={cur.operating} delta={vs(growth(cur.operating, prev?.operating))} fmt={money} />
              <Tile label={t.margin} value={margin(cur)} delta={vs(pointChange(margin(cur), margin(prev)))} fmt={(v) => `${v.toFixed(1)}%`} />
            </div>
          ) : (
            <div className="tiles">
              <Tile label={<>{t.yearOf(t.operating, cur.year)} <span className="help" title={t.noRevenue} aria-label={t.noRevenue}>?</span></>}
                value={cur.operating} delta={vs(growth(cur.operating, prev?.operating))} fmt={money} />
              <Tile label={t.net} value={cur.net} delta={vs(growth(cur.net, prev?.net))} fmt={money} />
            </div>
          )}
          {years.filter((y) => y[chartField] !== null && y[chartField] !== undefined).length > 1 && (
            <>
              <h3 className="chart-title">{t.byYear(hasRevenue ? revenueLabel : t.operating)}</h3>
              <YearBars data={years.map((y) => ({ year: y.year, value: y[chartField] }))}
                label={t.byYear(hasRevenue ? revenueLabel : t.operating)} format={money} />
            </>
          )}
          <Source text={t.sourceFinance(fin.year, fin.basis)} date={yearMonth(fin.rceptNo)} rceptNo={fin.rceptNo} />
        </>
      )}
      {/* 직원 현황(사업보고서)과 기업개황은 출처가 달라 따로 묶는다 */}
      {emp && (
        <>
          <dl className="kv">
            <div><dt>{t.employees}</dt><dd>{t.people(emp.count)}</dd></div>
            {(emp.tenure !== null || emp.salary !== null) && (
              <div><dt>{t.tenureSalary}</dt><dd>{t.tenureSalaryValue(emp.tenure !== null ? emp.tenure.toFixed(1) : null,
                emp.salary !== null ? money(emp.salary) : null)}</dd></div>
            )}
          </dl>
          <Source text={t.sourceEmployees} date={yearMonth(emp.rceptNo)} rceptNo={emp.rceptNo} />
        </>
      )}
      {info.length > 0 && (
        <>
          <dl className="kv">{info.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          <Source text={t.sourceCompany} />
        </>
      )}

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
  label: ReactNode
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

/** 경쟁사: 이 회사(굵게)와 같은 업종에서 매출이 큰 곳. 화면에 있는 회사는 회사 화면으로 */
function CompetitorsView({ data, hasDart }: { data: Competitors | undefined; hasDart: boolean }) {
  const h = t.competitorsHead
  const others = data?.rows.filter((r) => !r.self) ?? []
  return (
    <div className="module">
      <h3 className="sub-head">{t.competitors}</h3>
      {!data || others.length === 0 ? (
        <p className="not-found">{t.notFound(data || hasDart ? t.noCompetitors : t.noIndustry)}</p>
      ) : (
        <>
          <table className="peer-table">
            <thead><tr><th>{h.name}</th><th>{h.revenue}</th><th>{h.margin}</th></tr></thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.name + (r.self ? '*' : '')} className={r.self ? 'self' : undefined}>
                  <td>{r.key && !r.self ? <a className="plain-link" href={href.company(r.key)}>{r.name}</a> : r.name}</td>
                  <td>
                    {r.revenue === null ? '-' : r.rceptNo
                      ? <a className="plain-link" href={dartUrl(r.rceptNo)} target="_blank" rel="noreferrer noopener">{money(r.revenue)}</a>
                      : money(r.revenue)}
                    {r.revenue !== null && (
                      <span className="peer-sub">{[r.year, r.basis, r.revenueName === '영업수익' && t.operatingRevenue].filter(Boolean).join(' · ')}</span>
                    )}
                  </td>
                  <td>{r.margin === null ? '-' : `${r.margin.toFixed(1)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Source text={t.sourceCompetitors(data.industry)} />
        </>
      )}
    </div>
  )
}

/** 직무 환경·도구: 칸(클라우드, 데이터 플랫폼, BI, AI 도구)마다 공고에 많이 나온 도구와 공고 수 */
function ToolsView({ data, since }: { data: ToolsFound | undefined; since: string }) {
  const any = data?.slots.some((s) => s.items.length > 0)
  return (
    <div className="module">
      <h3 className="sub-head">{t.tools}</h3>
      {!data || !any ? <p className="not-found">{t.notFound(t.noTools)}</p> : (
        <>
          <dl className="kv">
            {data.slots.map((slot) => (
              <div key={slot.name}>
                <dt>{slot.name}</dt>
                <dd className="tool-list">
                  {slot.items.length === 0 ? <span className="muted">{t.toolsEmpty}</span>
                    : slot.items.map((i) => <span key={i.skill} className="tool-chip">{i.skill} <b>{i.count}</b></span>)}
                </dd>
              </div>
            ))}
          </dl>
          <Source text={t.sourceTools(data.postings, dateText(since, true))} />
        </>
      )}
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
        {total > 0 && (
          <span className="count">
            {jobs.length && !all ? t.pastMine(mineTotal, total) : past.length < total ? t.pastRecent(past.length, total) : t.pastAll(total)}
          </span>
        )}
      </div>
      {list.length === 0 ? <p className="note">{total === 0 ? t.noPast : t.noPastMine}</p> : (
        <div className="past-rows">
          {shown.map((p) => (
            <div key={p.id} className="past-row">
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
