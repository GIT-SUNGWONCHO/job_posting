import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { copy } from '../copy'
import { BarList, BubbleMap, Columns, MapLegend } from '../components/charts'
import { FilterSheet, type FilterSection } from '../components/FilterSheet'
import { Chip, DOWN_ICON, Empty, SectionTitle, SLIDERS_ICON } from '../components/ui'
import {
  BUCKETS, bins, bucketOf, currentOf, gaps, jobYears, matchAverages, mySkills, mySlice, otherDirections, periodStats,
  positions, roleToJob, strengths, sumSeries, targetJobs, weekBins, weekLabel, type Position, type Quadrant, type Slice,
} from '../lib/career'
import { dateText, monthOf } from '../lib/format'
import type { Match } from '../lib/matches'
import { deletePlan, loadPlans, monthView, newPlan, PLAN_KINDS, savePlan, type Plan, type PlanKind } from '../lib/plans'
import { careerTotals, loadProfile, saveProfile, yearsText, type Profile } from '../lib/profile'
import { href, type CareerSeg } from '../lib/route'
import type { CareerMetrics, Filters, JobType, Screen } from '../lib/types'

const t = copy.career

/** 할 일: 받기 전(undefined), 표가 없음(008 실행 전), 불러오기 실패 */
type PlansState = Plan[] | 'missing' | 'failed' | undefined

function PlansNote({ plans }: { plans: PlansState }) {
  if (plans === 'missing') return <p className="note urgent">{t.noTable}</p>
  if (plans === 'failed') return <p className="note urgent">{t.plansFailed}</p>
  if (plans === undefined) return <p className="note">{copy.load.loading}</p>
  return null
}
const SEGS: CareerSeg[] = ['market', 'position', 'plan']
const SKILLS_SHOWN = 8
const ZONES: Quadrant[] = ['apply', 'grow', 'keep']
const pct = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0)

function typeChip(f: Filters): string {
  const ts = f.company_types ?? []
  return ts.length === 0 ? copy.filter.allTypes : copy.filter.more(ts[0], ts.length - 1)
}

// 커리어 탭: 밑줄 탭 시장 · 내 위치 · 성장 계획. 기업 구분 칩은 세 탭 공통(개인 필터와 같다), 직무 칩은 시장에만.
// 숫자는 모두 공고에서 센 사실이다(docs/content-rules.md "커리어 지표"). AI 해석·제안은 아직 넣지 않는다.
export function Career({ screen, seg, filters, defaults, regions, onFilters, matches, today }: {
  screen: Screen
  seg: CareerSeg
  filters: Filters
  defaults: Filters
  regions: string[]
  onFilters: (f: Filters) => void
  matches: Map<string, Match>
  today: string
}) {
  const m = screen.career
  const [profile, setProfile] = useState<{ profile: Profile; version: number } | null | undefined>(undefined)
  const [plans, setPlans] = useState<PlansState>(undefined)
  const [sheet, setSheet] = useState<FilterSection | null>(null)
  const [job, setJob] = useState<string>('mine')
  useEffect(() => {
    let alive = true
    loadProfile().then((r) => alive && setProfile(r ?? null))
    loadPlans().then((p) => alive && setPlans(p))
    return () => {
      alive = false
    }
  }, [])
  const prof = profile?.profile ?? null

  const direction = screen.jobTypes.filter((j) => j.direction !== false)
  const myJobs = (filters.job_types ?? []).filter((id) => direction.some((j) => j.id === id))
  const { ctypes } = mySlice(screen.jobTypes, filters)
  const mine = useMemo(() => mySkills(prof), [prof])
  const toJob = useMemo(() => roleToJob(screen.profileOptions, screen.jobTypes), [screen])
  const pos = useMemo(() => {
    if (!m) return null
    return positions(m, direction, ctypes, mine, jobYears(prof, toJob), matchAverages(screen.postings, matches))
    // direction은 screen에서 나온다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m, screen, ctypes?.join(), mine, prof, toJob, matches])
  const hope = useMemo(() => new Set(targetJobs(prof, toJob)), [prof, toJob])

  async function addPlan(p: Plan): Promise<boolean> {
    const ok = await savePlan(p)
    // 고친 할 일은 제자리에서 바꾸고, 새 할 일은 끝에 붙인다
    if (ok) {
      setPlans((prev) => (!Array.isArray(prev) ? prev
        : prev.some((x) => x.id === p.id) ? prev.map((x) => (x.id === p.id ? p : x)) : [...prev, p]))
    }
    return ok
  }
  async function removePlan(id: string): Promise<boolean> {
    const ok = await deletePlan(id)
    if (ok) setPlans((prev) => (Array.isArray(prev) ? prev.filter((x) => x.id !== id) : prev))
    return ok
  }
  /** 다른 커리어를 목표에 넣는다: 그 직무로 이어지는 프로필 직무를 희망 직무에 더해 저장 */
  async function addTarget(jobId: string): Promise<boolean> {
    if (!profile) return false
    const role = screen.profileOptions?.roles.find((r) => (r.job_type ?? r.id) === jobId)
    if (!role || profile.profile.targetRoles.includes(role.id)) return false
    const next = { ...profile.profile, targetRoles: [...profile.profile.targetRoles, role.id] }
    const ok = await saveProfile(next, profile.version + 1)
    if (ok) setProfile({ profile: next, version: profile.version + 1 })
    return ok
  }

  const jobLabel = job === 'mine' ? t.jobChip(myJobs.length || direction.length) : direction.find((j) => j.id === job)?.short ?? job
  const head = (
    <>
      <div className="list-top"><h1>{t.title}</h1></div>
      <nav className="utabs career-tabs" aria-label={t.title}>
        {SEGS.map((s) => (
          <a key={s} href={href.careerSeg(s)} className={s === seg ? 'on' : undefined} aria-current={s === seg ? 'page' : undefined}>{t.segs[s]}</a>
        ))}
      </nav>
      <div className="chips scroll filter-row">
        <button type="button" className="chip icon" aria-label={copy.filter.all} onClick={() => setSheet('types')}>{SLIDERS_ICON}</button>
        {seg === 'market' && (
          <label className={job === 'mine' && !myJobs.length ? 'chip select-chip' : 'chip select-chip selected'}>
            <select aria-label={copy.filter.jobTypes} value={job} onChange={(e) => setJob(e.target.value)}>
              <option value="mine">{t.jobChip(myJobs.length || direction.length)}</option>
              {[...direction].sort((a, b) => Number(myJobs.includes(b.id)) - Number(myJobs.includes(a.id))).map((j) => (
                <option key={j.id} value={j.id}>{j.short ?? j.name}</option>
              ))}
            </select>
            <span>{jobLabel}</span>{DOWN_ICON}
          </label>
        )}
        <Chip selected={(filters.company_types ?? []).length > 0} onClick={() => setSheet('types')}>{typeChip(filters)}{DOWN_ICON}</Chip>
      </div>
      {sheet && (
        <FilterSheet value={filters} defaults={defaults} jobTypes={screen.jobTypes ?? []} regions={regions} focus={sheet}
          onClose={() => setSheet(null)} onSave={(f) => { onFilters(f); setSheet(null) }} />
      )}
    </>
  )

  if (!m || !pos) return <div className="page">{head}<Empty>{t.noData}</Empty></div>
  const needProfile = profile !== undefined && (!prof || (!prof.careers.length && !prof.skills.length))
  const slice: Slice = { jobs: job === 'mine' ? (myJobs.length ? myJobs : direction.map((j) => j.id)) : [job], ctypes }

  return (
    <div className="page career">
      {head}
      {seg === 'market' && <Market m={m} slice={slice} profile={prof} mine={mine} levels={screen.profileOptions?.skill_levels ?? []} />}
      {seg === 'position' && (needProfile ? <NoProfile /> : prof && <MapView pos={pos.list} demandLine={pos.demandLine} hope={hope} />)}
      {seg === 'plan' && (needProfile ? <NoProfile /> : prof && (
        <PlanView m={m} ctypes={ctypes} pos={pos.list} targets={[...hope]} mine={mine} jobTypes={screen.jobTypes}
          levels={screen.profileOptions?.skill_levels ?? []} plans={plans} month={monthOf(today)}
          onSave={addPlan} onRemove={removePlan} onTarget={addTarget}
          canTarget={(id) => !!screen.profileOptions?.roles.some((r) => (r.job_type ?? r.id) === id)} />
      ))}
    </div>
  )
}

function NoProfile() {
  return (
    <section className="section">
      <p className="note">{t.noProfile}</p>
      <a className="text-link" href={href.profile}>{t.toProfile} ›</a>
    </section>
  )
}

/** 시장: 새 공고(주별 · 일별), 많이 요구하는 경력(내 연차 구간), 많이 요구하는 스킬(내 스킬은 파랑 + 숙련도) */
function Market({ m, slice, profile, mine, levels }: {
  m: CareerMetrics
  slice: Slice
  profile: Profile | null
  mine: Map<string, number>
  levels: { level: number; name: string }[]
}) {
  const [weekly, setWeekly] = useState(true)
  const [allSkills, setAllSkills] = useState(false)
  const series = sumSeries(m, slice)
  // 수집 첫날은 그동안 열려 있던 공고가 한꺼번에 들어와 세지 않는다
  const from = periodStats(series, 0).from
  const weeks = weekBins(m.days, series.new, from).slice(-4)
  const cur = currentOf(m, slice)
  const years = profile ? careerTotals(profile)[1] : null
  const myBucket = years !== null && profile?.careers.length ? bucketOf(years) : null
  const levelName = (lv: number) => levels.find((l) => l.level === lv)?.name
  const daily = bins(m.days, series.new, Math.max(from, m.days.length - 14)).bins
  const thisWeek = weeks[weeks.length - 1]
  const lastWeek = weeks[weeks.length - 2]
  const columns = weekly
    ? weeks.map((w, i) => ({ key: w.start, label: i === weeks.length - 1 ? t.thisWeek : weekLabel(w.start), value: w.value, on: i === weeks.length - 1 }))
    : daily.map((d, i) => ({ key: d.start, label: dateText(d.start), value: d.value, on: i === daily.length - 1 }))
  const skills = allSkills ? cur.skills.slice(0, 20) : cur.skills.slice(0, SKILLS_SHOWN)
  return (
    <>
      <section className="section">
        <SectionTitle right={(
          <span className="seg2" role="group" aria-label={t.newPostings}>
            <button type="button" className={weekly ? 'on' : ''} aria-pressed={weekly} onClick={() => setWeekly(true)}>{t.weeklyShort}</button>
            <button type="button" className={weekly ? '' : 'on'} aria-pressed={!weekly} onClick={() => setWeekly(false)}>{t.dailyShort}</button>
          </span>
        )}>{t.newPostings}</SectionTitle>
        {columns.length === 0 ? <p className="note">{t.firstDay}</p> : <Columns data={columns} label={weekly ? t.weekly : t.daily} />}
        {thisWeek && (
          <div className="week-kv">
            <span>{t.thisWeekDays(thisWeek.days)}</span><b className="on">{t.count(thisWeek.value ?? 0)}</b>
            {lastWeek && <><span>{t.lastWeek}</span><b>{t.count(lastWeek.value ?? 0)}</b></>}
          </div>
        )}
      </section>

      <section className="section">
        <SectionTitle info={<>{t.careerDistNote(cur.total)}{myBucket && years !== null ? ` · ${t.myBucket(yearsText(Math.floor(years * 10) / 10))}` : ''}</>}>{t.careerDist}</SectionTitle>
        <BarList max={100} rows={BUCKETS.map((b) => ({
          key: b, label: t.buckets[b], value: pct(cur.career[b], cur.total), text: `${pct(cur.career[b], cur.total)}%`,
          on: b === myBucket, tag: b === myBucket ? t.myBucketTag : undefined,
        }))} />
      </section>

      <section className="section">
        <SectionTitle info={t.topSkillsNote(cur.withBody)}>{t.topSkills}</SectionTitle>
        <BarList max={100} rows={skills.map(([name, n]) => ({
          key: name, label: name, value: pct(n, cur.withBody), text: `${pct(n, cur.withBody)}%`,
          on: mine.has(name), tag: mine.has(name) ? levelName(mine.get(name)!) ?? t.mine : undefined,
        }))} />
        {!allSkills && cur.skills.length > SKILLS_SHOWN && (
          <button type="button" className="btn block more" onClick={() => setAllSkills(true)}>{t.more(Math.min(20, cur.skills.length) - SKILLS_SHOWN)}</button>
        )}
      </section>
    </>
  )
}

/** 내 위치: 직무 지도와 주력 · 도전 · 틈새 묶음(모두 접고 희망 직무 줄만, 누르면 펼침) */
function MapView({ pos, demandLine, hope }: { pos: Position[]; demandLine: number; hope: Set<string> }) {
  return (
    <section className="section">
      <SectionTitle info={<>{t.mapNote}<br />{t.fitHelp}</>}>{t.map}</SectionTitle>
      <MapLegend />
      <div className="map-wrap">
        <span className="axis-up">↑ {t.axisDemand}</span>
        <BubbleMap list={pos} demandLine={demandLine} hope={hope} label={t.map} />
      </div>
      <div className="zones">
        {ZONES.map((q) => <ZoneGroup key={q} q={q} list={pos.filter((p) => p.quadrant === q).sort((a, b) => b.open - a.open)} hope={hope} />)}
      </div>
    </section>
  )
}

function ZoneGroup({ q, list, hope }: { q: Quadrant; list: Position[]; hope: Set<string> }) {
  const [open, setOpen] = useState(false)
  const shown = open ? list : list.filter((p) => hope.has(p.id))
  const rest = list.length - shown.length
  return (
    <div className={q === 'apply' ? 'zone-group main' : 'zone-group'}>
      <button type="button" className="zone-head" aria-expanded={open} onClick={() => setOpen(!open)} disabled={list.length === 0}>
        <b>{t.zones[q]}</b><span className="zone-count">{list.length}</span><span className={open ? 'chev up' : 'chev'}>{DOWN_ICON}</span>
      </button>
      {shown.map((p) => (
        <div key={p.id} className={hope.has(p.id) ? 'zone-row hope' : 'zone-row'}>
          <span>{p.name}</span>
          <span className="muted-sm">{p.fit}% <span className="sep" /> {t.open(p.open)}</span>
        </div>
      ))}
      {!open && rest > 0 && shown.length > 0 && <button type="button" className="zone-more" onClick={() => setOpen(true)}>{t.restCount(rest)}</button>}
    </div>
  )
}

/** 성장 계획: 목표 커리어(희망 직무)를 고르면 그 직무의 채우면 좋은 스킬, 아래 다른 커리어(목표에 넣기), 이번 달 할 일 */
function PlanView({ m, ctypes, pos, targets, mine, jobTypes, levels, plans, month, onSave, onRemove, onTarget, canTarget }: {
  m: CareerMetrics
  ctypes: string[] | null
  pos: Position[]
  targets: string[]
  mine: Map<string, number>
  jobTypes: JobType[]
  levels: { level: number; name: string }[]
  plans: PlansState
  month: string
  onSave: (p: Plan) => Promise<boolean>
  onRemove: (id: string) => Promise<boolean>
  onTarget: (jobId: string) => Promise<boolean>
  canTarget: (jobId: string) => boolean
}) {
  const goals = targets.map((id) => pos.find((p) => p.id === id)).filter((p): p is Position => !!p)
  const [pick, setPick] = useState(goals[0]?.id ?? '')
  const [showHave, setShowHave] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const goal = goals.find((p) => p.id === pick) ?? goals[0]
  const others = otherDirections(pos, targets, 3)
  const levelName = (lv: number) => levels.find((l) => l.level === lv)?.name ?? t.levelNone
  const withBody = goal ? currentOf(m, { jobs: [goal.id], ctypes }).withBody : 0
  const fill = goal ? gaps(goal.skills, mine, 6) : []
  const have = goal ? strengths(goal.skills, mine, 20) : []
  const name = (id: string) => jobTypes.find((j) => j.id === id)?.short ?? id
  return (
    <>
      <section className="section">
        <SectionTitle>{t.goals}</SectionTitle>
        {goals.length === 0 ? <p className="note">{t.noGoals}</p> : (
          <>
            <div className="pills">
              {goals.map((p) => (
                <button key={p.id} type="button" className={p.id === goal?.id ? 'pill on' : 'pill'} aria-pressed={p.id === goal?.id} onClick={() => setPick(p.id)}>{name(p.id)}</button>
              ))}
              <a className="pill add" href={href.profile}>{t.addGoal}</a>
            </div>
            {goal && (
              <>
                <div className="intro-meta goal-meta"><span>{t.axisFit} <b>{goal.fit ?? '-'}%</b></span><span className="sep" /><span>{t.openShort} <b>{goal.open}</b></span></div>
                <div className="section-title sub"><h3 className="h3">{t.fill}</h3></div>
                {fill.length === 0 ? <p className="note">{t.noFill}</p> : (
                  <BarList max={100} rows={fill.map((g) => ({
                    key: g.name, label: g.name, value: pct(g.count, withBody), text: `${pct(g.count, withBody)}%`,
                    on: false, level: levelName(g.level), levelOn: g.level > 0,
                  }))} />
                )}
                {have.length > 0 && (
                  <button type="button" className="have-box" aria-expanded={showHave} onClick={() => setShowHave(!showHave)}>
                    <span>{t.haveSkills}</span><span className="muted-sm">{have.length}<span className={showHave ? 'chev up' : 'chev'}>{DOWN_ICON}</span></span>
                  </button>
                )}
                {showHave && <p className="have-list">{have.join(' · ')}</p>}
              </>
            )}
          </>
        )}
      </section>

      <section className="section">
        <SectionTitle info={t.othersNote}>{t.others}</SectionTitle>
        <div className="other-rows">
          {others.map((p) => (
            <div key={p.id} className="other-row">
              <span className="other-main"><b>{p.name}</b><span className="muted-sm">{p.fit}% <span className="sep" /> {t.open(p.open)}</span></span>
              {canTarget(p.id) && (
                <button type="button" className="text-link" disabled={busy !== null} onClick={async () => { setBusy(p.id); await onTarget(p.id); setBusy(null) }}>
                  {busy === p.id ? t.saving : t.toGoal}
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      <Todos plans={plans} month={month} onSave={onSave} onRemove={onRemove} />
    </>
  )
}

function Todos({ plans, month, onSave, onRemove }: {
  plans: PlansState
  month: string
  onSave: (p: Plan) => Promise<boolean>
  onRemove: (id: string) => Promise<boolean>
}) {
  const [text, setText] = useState('')
  const [kind, setKind] = useState<PlanKind>('study')
  const [failed, setFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const view = monthView(Array.isArray(plans) ? plans : [], month)

  async function run(job: Promise<boolean>) {
    setSaving(true)
    const ok = await job
    setSaving(false)
    setFailed(!ok)
    return ok
  }
  async function add(e: FormEvent) {
    e.preventDefault()
    if (!text.trim()) return
    if (await run(onSave(newPlan(month, text, kind)))) setText('')
  }

  const item = (p: Plan) => (
    <div key={p.id} className="todo">
      <label className="todo-check">
        <input type="checkbox" checked={p.done} disabled={saving} onChange={() => run(onSave({ ...p, done: !p.done }))} />
        <span className={p.done ? 'todo-text done' : 'todo-text'}>{p.text}</span>
      </label>
      <span className="badge">{t.kinds[p.kind]}</span>
      <button type="button" className="small-del" disabled={saving} onClick={() => run(onRemove(p.id))}>{t.remove}</button>
    </div>
  )

  return (
    <section className="section">
      <SectionTitle count={month.replace('-', '.')}>{t.todo}</SectionTitle>
      {!Array.isArray(plans) ? <PlansNote plans={plans} /> : (
        <>
          {view.now.length === 0 ? <p className="note">{t.todoEmpty}</p> : <div className="todos">{view.now.map(item)}</div>}
          {view.carried.length > 0 && (
            <>
              <h3 className="h3">{t.carried}</h3>
              <div className="todos">{view.carried.map(item)}</div>
            </>
          )}
          <form className="todo-add" onSubmit={add}>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder={t.todoPlaceholder} aria-label={t.todo} />
            <select value={kind} onChange={(e) => setKind(e.target.value as PlanKind)} aria-label={t.kind}>
              {PLAN_KINDS.map((k) => <option key={k} value={k}>{t.kinds[k]}</option>)}
            </select>
            <button type="submit" className="btn" disabled={saving || !text.trim()}>{t.add}</button>
          </form>
          {failed && <p className="note urgent">{t.failed}</p>}
        </>
      )}
    </section>
  )
}
