import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { copy } from '../copy'
import { BarList, ColumnChart, PositionMap } from '../components/charts'
import { Chip, Empty, SectionTitle } from '../components/ui'
import {
  BUCKETS, bins, bucketOf, currentOf, gaps, jobYears, matchAverages, mySkills, otherDirections, periods, periodStats,
  positions, roleToJob, strengths, sumSeries, targetJobs, type Position, type Slice,
} from '../lib/career'
import { dateText, monthOf, signed } from '../lib/format'
import type { Match } from '../lib/matches'
import { deletePlan, loadPlans, monthView, newPlan, PLAN_KINDS, savePlan, type Plan, type PlanKind } from '../lib/plans'
import { careerTotals, loadProfile, yearsText, type Profile } from '../lib/profile'
import { href, type CareerSeg } from '../lib/route'
import type { CareerMetrics, Filters, Screen } from '../lib/types'

const t = copy.career
const SEGS: CareerSeg[] = ['market', 'position', 'plan']
const SKILLS_SHOWN = 15
const MY_SKILLS_SHOWN = 10

// 커리어 탭(와이어프레임 C1~C3): 시장 / 내 위치 / 성장 계획.
// 숫자는 모두 공고에서 센 사실이다(docs/content-rules.md "커리어 지표"). AI 해석·제안은 아직 넣지 않는다.
export function Career({ screen, seg, filters, matches, today }: {
  screen: Screen
  seg: CareerSeg
  filters: Filters
  matches: Map<string, Match>
  today: string
}) {
  const m = screen.career
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined)
  const [plans, setPlans] = useState<Plan[] | null | undefined>(undefined)
  useEffect(() => {
    let alive = true
    loadProfile().then((r) => alive && setProfile(r?.profile ?? null))
    loadPlans().then((p) => alive && setPlans(p))
    return () => {
      alive = false
    }
  }, [])

  const direction = screen.jobTypes.filter((j) => j.direction !== false)
  const myJobs = (filters.job_types ?? []).filter((id) => direction.some((j) => j.id === id))
  const ctypes = filters.company_types?.length ? filters.company_types : null
  const mine = useMemo(() => mySkills(profile ?? null), [profile])
  const toJob = useMemo(() => roleToJob(screen.profileOptions, screen.jobTypes), [screen])
  const pos = useMemo(() => {
    if (!m) return null
    const years = jobYears(profile ?? null, toJob)
    return positions(m, direction, ctypes, mine, years, matchAverages(screen.postings, matches))
    // direction은 screen에서 나온다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m, screen, ctypes?.join(), mine, profile, toJob, matches])

  async function addPlan(p: Plan): Promise<boolean> {
    const ok = await savePlan(p)
    // 고친 할 일은 제자리에서 바꾸고, 새 할 일은 끝에 붙인다
    if (ok) setPlans((prev) => (prev?.some((x) => x.id === p.id) ? prev.map((x) => (x.id === p.id ? p : x)) : [...(prev ?? []), p]))
    return ok
  }
  async function removePlan(id: string): Promise<boolean> {
    const ok = await deletePlan(id)
    if (ok) setPlans((prev) => (prev ?? []).filter((x) => x.id !== id))
    return ok
  }

  const head = (
    <header className="page-head">
      <h1>{t.title}</h1>
      {m && (
        <div className="page-sub">
          {t.basis(dateText(m.since), m.days.length, ctypes ? t.typesOf(ctypes) : t.allTypes)}
        </div>
      )}
      <nav className="seg" aria-label={t.title}>
        {SEGS.map((s) => (
          <a key={s} href={href.careerSeg(s)} className={s === seg ? 'on' : undefined} aria-current={s === seg ? 'page' : undefined}>
            {t.segs[s]}
          </a>
        ))}
      </nav>
    </header>
  )

  if (!m || !pos) return <div className="page">{head}<Empty>{t.noData}</Empty></div>
  const needProfile = profile !== undefined && (!profile || (!profile.careers.length && !profile.skills.length))

  return (
    <div className="page career">
      {head}
      {seg === 'market' && <Market m={m} screen={screen} myJobs={myJobs} ctypes={ctypes} profile={profile ?? null} mine={mine} />}
      {seg === 'position' && (needProfile ? <NoProfile /> : profile && (
        <PositionView m={m} pos={pos.list} demandLine={pos.demandLine} myJobs={myJobs} ctypes={ctypes} mine={mine}
          levels={screen.profileOptions?.skill_levels ?? []} plans={plans} month={monthOf(today)} onAdd={addPlan} />
      ))}
      {seg === 'plan' && (needProfile ? <NoProfile /> : profile && (
        <PlanView pos={pos.list} targets={targetJobs(profile, toJob)} mine={mine} plans={plans} month={monthOf(today)}
          onSave={addPlan} onRemove={removePlan} />
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

const pct = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0)

/** 시장(C1): 직무·기간 고르기 → 새 공고, 열린 공고, 날짜별 막대, 경력 요구, 직무별 열린 공고, 많이 요구하는 스킬 */
function Market({ m, screen, myJobs, ctypes, profile, mine }: {
  m: CareerMetrics
  screen: Screen
  myJobs: string[]
  ctypes: string[] | null
  profile: Profile | null
  mine: Map<string, number>
}) {
  const options = periods(m)
  const [job, setJob] = useState<string>('mine')
  const [days, setDays] = useState<number>(options.includes(7) ? 7 : 0)
  const direction = screen.jobTypes.filter((j) => j.direction !== false)
  const slice: Slice = { jobs: job === 'mine' ? (myJobs.length ? myJobs : direction.map((j) => j.id)) : [job], ctypes }
  const series = sumSeries(m, slice)
  const stats = periodStats(series, days)
  const cur = currentOf(m, slice)
  const data = bins(m.days, series.new, stats.from)
  const weekly = data.length > 1 && data[0].start !== data[0].end
  const label = t.period(days)
  const change = stats.prevSum ? `${signed(Math.round(((stats.newSum - stats.prevSum) / stats.prevSum) * 100))}%` : null
  const years = profile ? careerTotals(profile)[1] : null
  const myBucket = years !== null && profile?.careers.length ? bucketOf(years) : null
  // 직무별 열린 공고: 같은 기업 구분, 모든 직무(내 직무 먼저 강조)
  const byJob = direction.map((j) => {
    const s = sumSeries(m, { jobs: [j.id], ctypes })
    const n = s.open.length
    return { j, open: s.open[n - 1] ?? 0, change: n > 7 ? s.open[n - 1] - s.open[n - 8] : null }
  }).sort((a, b) => b.open - a.open)

  return (
    <>
      <div className="career-filters">
        <div className="chips scroll" role="group" aria-label={copy.filter.jobTypes}>
          <Chip selected={job === 'mine'} onClick={() => setJob('mine')}>{t.myJobs}</Chip>
          {[...direction].sort((a, b) => Number(myJobs.includes(b.id)) - Number(myJobs.includes(a.id))).map((j) => (
            <Chip key={j.id} selected={job === j.id} onClick={() => setJob(j.id)}>{j.short ?? j.name}</Chip>
          ))}
        </div>
        <div className="chips" role="group" aria-label="기간">
          {[...options, 0].map((d) => <Chip key={d} selected={days === d} onClick={() => setDays(d)}>{t.period(d)}</Chip>)}
        </div>
      </div>

      <section className="section">
        <div className="tiles">
          <div className="tile">
            <span className="tile-label">{t.newPostings} · {label}</span>
            <b className="tile-value">{stats.newSum.toLocaleString()}</b>
            <span className="tile-delta">{change ? t.vsPrev(label, change) : t.noPrev}</span>
          </div>
          <div className="tile">
            <span className="tile-label">{t.openPostings}</span>
            <b className="tile-value">{stats.openNow.toLocaleString()}</b>
            <span className="tile-delta">{t.openFrom(signed(stats.openNow - stats.openFrom))}</span>
          </div>
        </div>
        <h3 className="chart-title">{weekly ? t.weekly : t.daily}</h3>
        <ColumnChart data={data} label={weekly ? t.weekly : t.daily} />
        {stats.from === 0 && <p className="note small">{t.firstDay}</p>}
      </section>

      <section className="section">
        <SectionTitle right={<span className="count">{t.count(cur.total)}</span>}>{t.careerDist}</SectionTitle>
        <p className="note small">{t.careerDistNote}{myBucket && years !== null ? ` · ${t.myBucket(yearsText(Math.floor(years * 10) / 10))}` : ''}</p>
        <BarList rows={BUCKETS.map((b) => ({
          key: b, label: t.buckets[b], value: cur.career[b], text: t.share(cur.career[b], pct(cur.career[b], cur.total)),
          on: b === myBucket, tag: b === myBucket ? t.myBucketTag : undefined,
        }))} />
      </section>

      <section className="section">
        <SectionTitle>{t.byJob}</SectionTitle>
        <p className="note small">{t.byJobNote}</p>
        <BarList rows={byJob.map(({ j, open, change: c }) => ({
          key: j.id, label: j.short ?? j.name, value: open,
          text: c === null ? open.toLocaleString() : `${open.toLocaleString()} (${signed(c)})`,
          on: myJobs.includes(j.id), tag: myJobs.includes(j.id) ? t.myJobs : undefined,
          selected: job === j.id, onClick: () => setJob(job === j.id ? 'mine' : j.id),
        }))} />
      </section>

      <section className="section">
        <SectionTitle>{t.topSkills}</SectionTitle>
        <p className="note small">{t.topSkillsNote(cur.withBody)}</p>
        <BarList rows={cur.skills.slice(0, SKILLS_SHOWN).map(([name, n]) => ({
          key: name, label: name, value: n, text: t.share(n, pct(n, cur.withBody)),
          on: mine.has(name), tag: mine.has(name) ? t.mine : undefined,
        }))} />
      </section>
    </>
  )
}

/** 내 위치(C2): 포지션 맵과 표, 내 스킬의 수요, 채우면 좋은 것 */
function PositionView({ m, pos, demandLine, myJobs, ctypes, mine, levels, plans, month, onAdd }: {
  m: CareerMetrics
  pos: Position[]
  demandLine: number
  myJobs: string[]
  ctypes: string[] | null
  mine: Map<string, number>
  levels: { level: number; name: string }[]
  plans: Plan[] | null | undefined
  month: string
  onAdd: (p: Plan) => Promise<boolean>
}) {
  const [allSkills, setAllSkills] = useState(false)
  const mySet = new Set(myJobs)
  const cur = currentOf(m, { jobs: myJobs.length ? myJobs : null, ctypes })
  const counts = new Map(cur.skills)
  const levelName = (lv: number) => levels.find((l) => l.level === lv)?.name ?? t.levelNone
  const mySkillRows = [...mine.entries()].map(([name, lv]) => ({ name, lv, n: counts.get(name) ?? 0 })).sort((a, b) => b.n - a.n)
  const fill = gaps(cur.skills, mine, 8)
  const planned = new Set((plans ?? []).filter((p) => !p.done && p.skill).map((p) => p.skill!))
  const quads = (['apply', 'grow', 'keep', 'reduce'] as const).map((q) => ({ q, list: pos.filter((p) => p.quadrant === q && p.fit !== null) }))

  return (
    <>
      <section className="section">
        <SectionTitle>{t.map}</SectionTitle>
        <p className="note small">{t.mapNote}</p>
        <PositionMap list={pos} demandLine={demandLine} mine={mySet} label={t.map} />
        <div className="legend">
          <span><i className="key on" />{t.legendMine}</span>
          <span><i className="key" />{t.legendOther}</span>
        </div>
        <p className="note small">{t.fitHelp}</p>
        {quads.map(({ q, list }) => list.length > 0 && (
          <div key={q} className="quad-group">
            <h3>{t.quadrants[q]} <span className="note small">{t.quadrantHelp[q]}</span></h3>
            {list.sort((a, b) => b.open - a.open).map((p) => (
              <div key={p.id} className="quad-row">
                <span className="quad-name">{p.name}{mySet.has(p.id) && <span className="bar-tag">{t.myJobs}</span>}</span>
                <span className="quad-meta">
                  {[
                    `${t.open(p.open)}${p.change !== null ? ` (${signed(p.change)})` : ''}`,
                    t.fit(p.fit),
                    p.years > 0 && t.years(yearsText(Math.round(p.years * 10) / 10)),
                    p.match && t.matchAvg(p.match.avg, p.match.n),
                  ].filter(Boolean).join(' · ')}
                </span>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section className="section">
        <SectionTitle>{t.mySkillDemand}</SectionTitle>
        <p className="note small">{t.mySkillDemandNote} · {t.topSkillsNote(cur.withBody)}</p>
        <BarList rows={(allSkills ? mySkillRows : mySkillRows.slice(0, MY_SKILLS_SHOWN)).map((r) => ({
          key: r.name, label: r.name, value: r.n, text: t.share(r.n, pct(r.n, cur.withBody)), on: true, tag: levelName(r.lv),
        }))} />
        {!allSkills && mySkillRows.length > MY_SKILLS_SHOWN && (
          <button type="button" className="text-link" onClick={() => setAllSkills(true)}>{t.more(mySkillRows.length - MY_SKILLS_SHOWN)}</button>
        )}
      </section>

      <section className="section">
        <SectionTitle>{t.fill}</SectionTitle>
        <p className="note small">{t.fillNote}</p>
        {plans === null && <p className="note urgent">{t.noTable}</p>}
        <div className="rows">
          {fill.map((g) => (
            <div key={g.name} className="fill-row">
              <span className="row-main">
                <span className="row-title">{g.name}</span>
                <span className="row-meta">
                  <span>{t.share(g.count, pct(g.count, cur.withBody))}</span>
                  <span>{levelName(g.level)}</span>
                </span>
              </span>
              {planned.has(g.name)
                ? <span className="note small">{t.inPlan}</span>
                : <AddPlanButton disabled={plans === null} onAdd={() => onAdd(newPlan(month, t.planText(g.name), 'study', g.name))} />}
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

function AddPlanButton({ disabled, onAdd }: { disabled: boolean; onAdd: () => Promise<boolean> }) {
  const [state, setState] = useState<'idle' | 'saving' | 'failed'>('idle')
  return (
    <span className="fill-action">
      {state === 'failed' && <span className="note urgent small">{t.failed}</span>}
      <button type="button" className="btn small" disabled={disabled || state === 'saving'}
        onClick={async () => { setState('saving'); setState((await onAdd()) ? 'idle' : 'failed') }}>{t.addPlan}</button>
    </span>
  )
}

/** 성장 계획(C3): 목표 방향, 다른 방향, 이번 달 할 일, 월간 커리어 리포트(나중에) */
function PlanView({ pos, targets, mine, plans, month, onSave, onRemove }: {
  pos: Position[]
  targets: string[]
  mine: Map<string, number>
  plans: Plan[] | null | undefined
  month: string
  onSave: (p: Plan) => Promise<boolean>
  onRemove: (id: string) => Promise<boolean>
}) {
  const goals = targets.map((id) => pos.find((p) => p.id === id)).filter((p): p is Position => !!p)
  const others = otherDirections(pos, targets, 4)
  return (
    <>
      <section className="section">
        <SectionTitle>{t.goals}</SectionTitle>
        <p className="note small">{t.goalsNote}</p>
        {goals.length === 0 ? <p className="note">{t.noGoals}</p> : (
          <div className="goals">
            {goals.map((p) => (
              <div key={p.id} className="goal">
                <div className="goal-head">
                  <h3>{p.name}</h3>
                  <span className="quad-chip">{t.quadrants[p.quadrant]}</span>
                </div>
                <div className="quad-meta">
                  {[
                    `${t.open(p.open)}${p.change !== null ? ` (${signed(p.change)})` : ''}`,
                    t.fit(p.fit),
                    t.years(yearsText(Math.round(p.years * 10) / 10)),
                    p.match && t.matchAvg(p.match.avg, p.match.n),
                  ].filter(Boolean).join(' · ')}
                </div>
                <div className="skill-line">
                  <span>{t.strengths}</span>
                  <div className="chips wrap small">{strengths(p.skills, mine, 5).map((s) => <span key={s} className="chip">{s}</span>)}</div>
                </div>
                <div className="skill-line">
                  <span>{t.toFill}</span>
                  <div className="chips wrap small">{gaps(p.skills, mine, 5).map((g) => <span key={g.name} className="chip gap">{g.name}</span>)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="section">
        <SectionTitle>{t.others}</SectionTitle>
        <p className="note small">{t.othersNote}</p>
        <div className="rows">
          {others.map((p) => (
            <div key={p.id} className="quad-row">
              <span className="quad-name">{p.name}<span className="quad-chip">{t.quadrants[p.quadrant]}</span></span>
              <span className="quad-meta">{[t.open(p.open), t.fit(p.fit), p.years > 0 && t.years(yearsText(Math.round(p.years * 10) / 10))].filter(Boolean).join(' · ')}</span>
            </div>
          ))}
        </div>
      </section>

      <Todos plans={plans} month={month} onSave={onSave} onRemove={onRemove} />

      <section className="section">
        <SectionTitle>{t.monthly}</SectionTitle>
        <p className="note">{t.monthlyLater}</p>
      </section>
    </>
  )
}

function Todos({ plans, month, onSave, onRemove }: {
  plans: Plan[] | null | undefined
  month: string
  onSave: (p: Plan) => Promise<boolean>
  onRemove: (id: string) => Promise<boolean>
}) {
  const [text, setText] = useState('')
  const [kind, setKind] = useState<PlanKind>('study')
  const [failed, setFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const view = monthView(plans ?? [], month)

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
      <span className="quad-chip">{t.kinds[p.kind]}</span>
      <button type="button" className="text-link danger" disabled={saving} onClick={() => run(onRemove(p.id))}>{t.remove}</button>
    </div>
  )

  return (
    <section className="section">
      <SectionTitle right={<span className="count">{month.replace('-', '.')}</span>}>{t.todo}</SectionTitle>
      {plans === null ? <p className="note urgent">{t.noTable}</p> : (
        <>
          {view.now.length === 0 ? <p className="note">{t.todoEmpty}</p> : <div className="todos">{view.now.map(item)}</div>}
          {view.carried.length > 0 && (
            <>
              <h3 className="sub-head">{t.carried}</h3>
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
