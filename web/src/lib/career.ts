// 커리어 탭 계산. 시장 지표(screen.career)는 src/jobpost/career.py가 만들고, 여기서는 내 필터·프로필에 맞게 더하고 비교한다.
// 계산법은 docs/content-rules.md "커리어 지표"에 적은 것과 같게 둔다(바꾸면 그 문서도 고친다).
import { months, type Profile } from './profile'
import type { Match } from './matches'
import type { CareerBucket, CareerMetrics, Filters, JobType, Posting, ProfileOptions } from './types'

export const BUCKETS: CareerBucket[] = ['0-3', '3-7', '7-12', '12+', 'any']
/** 스킬 적합도를 셀 때 보는 요구 스킬 수(공고 수 많은 순) */
export const FIT_TOP = 20
/** 스킬 적합도와 포지션 맵의 가로 기준선(%) */
export const FIT_LINE = 50
/** 이 숙련도부터 "가진 스킬"로 센다. 그 아래(기초, 안 고름)는 절반 */
export const FIT_LEVEL = 2
/** 기간 고르기: 날 수. 0은 수집을 시작한 날부터 */
export const PERIODS = [7, 30, 182, 365]
/** 이 날 수보다 길면 막대를 주 단위로 묶는다 */
const WEEKLY_OVER = 60

/** null은 전부(필터를 안 건 것) */
export interface Slice {
  jobs: string[] | null
  ctypes: string[] | null
}

/** 내 직무(필터의 직무 유형 중 커리어 방향인 것, 비면 방향 전부)와 내 기업 구분(비면 전부) */
export function mySlice(jobTypes: JobType[], filters: Pick<Filters, 'job_types' | 'company_types'>): { jobs: string[]; ctypes: string[] | null } {
  const direction = jobTypes.filter((j) => j.direction !== false).map((j) => j.id)
  const mine = (filters.job_types ?? []).filter((id) => direction.includes(id))
  return { jobs: mine.length ? mine : direction, ctypes: filters.company_types?.length ? filters.company_types : null }
}

function inSlice(key: string, s: Slice): boolean {
  const [job, ctype] = key.split('|')
  return (!s.jobs || s.jobs.includes(job)) && (!s.ctypes || s.ctypes.includes(ctype))
}

/** 날짜별 열린 공고와 새 공고를 묶음들에 걸쳐 더한다 */
export function sumSeries(m: CareerMetrics, s: Slice): { open: number[]; new: (number | null)[] } {
  const n = m.days.length
  const open = new Array<number>(n).fill(0)
  // 묶음이 하나도 없는 직무·기업 구분도 0건이다(세지 않는 날은 수집 첫날뿐)
  const fresh = new Array<number | null>(n).fill(0)
  for (const [key, v] of Object.entries(m.series)) {
    if (!inSlice(key, s)) continue
    for (let i = 0; i < n; i++) {
      open[i] += v.open[i] ?? 0
      fresh[i] = (fresh[i] ?? 0) + (v.new[i] ?? 0)
    }
  }
  // 수집 첫날은 늘 세지 않는다(묶음이 하나도 없어도)
  if (n) fresh[0] = null
  return { open, new: fresh }
}

/** 고를 수 있는 기간: 새 공고를 셀 수 있는 날(첫날 뺀 날) 수가 그만큼 있는 것만 */
export function periods(m: CareerMetrics): number[] {
  return PERIODS.filter((d) => m.days.length - 1 >= d)
}

export interface PeriodStats {
  /** 기간의 첫 날 index */
  from: number
  newSum: number
  /** 바로 앞 같은 길이 기간의 새 공고. 데이터가 모자라면 null */
  prevSum: number | null
  openNow: number
  openFrom: number
}

/** days: 기간 날 수(0은 전체) */
export function periodStats(series: { open: number[]; new: (number | null)[] }, days: number): PeriodStats {
  const len = series.open.length
  const from = days ? Math.max(0, len - days) : 0
  const sum = (a: number, b: number) => series.new.slice(a, b).reduce<number>((s, x) => s + (x ?? 0), 0)
  // 앞 기간도 첫날(null)을 빼고 온전히 있어야 비교한다
  const prevSum = days && len - 2 * days >= 1 ? sum(len - 2 * days, len - days) : null
  return { from, newSum: sum(from, len), prevSum, openNow: series.open[len - 1] ?? 0, openFrom: series.open[from] ?? 0 }
}

export interface Bin {
  start: string
  end: string
  value: number | null
}

/** 막대 하나 = 하루, 기간이 길면 7일. 끝(오늘)에서부터 묶고, 7일이 안 되는 맨 앞 묶음은 뺀다
 * (짧은 막대가 수요가 준 것처럼 보이지 않게). size는 막대 하나의 날 수 */
export function bins(days: string[], values: (number | null)[], from: number): { bins: Bin[]; size: number } {
  const size = days.length - from > WEEKLY_OVER ? 7 : 1
  const out: Bin[] = []
  for (let end = days.length; end - size >= from; end -= size) {
    const start = end - size
    const vs = values.slice(start, end)
    const value = vs.every((v) => v === null) ? null : vs.reduce<number>((s, v) => s + (v ?? 0), 0)
    out.unshift({ start: days[start], end: days[end - 1], value })
  }
  return { bins: out, size }
}

export interface Current {
  career: Record<CareerBucket, number>
  /** 스킬별 공고 수, 많은 순 */
  skills: [string, number][]
  withBody: number
  total: number
}

export function currentOf(m: CareerMetrics, s: Slice): Current {
  const career = Object.fromEntries(BUCKETS.map((b) => [b, 0])) as Record<CareerBucket, number>
  const skills = new Map<string, number>()
  let withBody = 0
  for (const [key, v] of Object.entries(m.current)) {
    if (!inSlice(key, s)) continue
    for (const b of BUCKETS) career[b] += v.career[b] ?? 0
    for (const [name, n] of v.skills) skills.set(name, (skills.get(name) ?? 0) + n)
    withBody += v.withBody
  }
  const total = BUCKETS.reduce((t, b) => t + career[b], 0)
  return { career, skills: [...skills.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])), withBody, total }
}

export function bucketOf(years: number): CareerBucket {
  if (years < 3) return '0-3'
  if (years < 7) return '3-7'
  if (years < 12) return '7-12'
  return '12+'
}

/** 프로필 스킬 이름 → 숙련도 */
export function mySkills(p: Profile | null): Map<string, number> {
  return new Map((p?.skills ?? []).map((s) => [s.name, s.level]))
}

const weightOf = (level: number | undefined) => (level === undefined ? 0 : level >= FIT_LEVEL ? 1 : 0.5)

/** 스킬 적합도(%): 그 직무 공고가 많이 요구하는 스킬(상위 FIT_TOP개, 요구한 공고 수로 가중) 중 내가 가진 비율 */
export function skillFit(skills: [string, number][], mine: Map<string, number>): number | null {
  const top = skills.slice(0, FIT_TOP)
  const total = top.reduce((s, [, n]) => s + n, 0)
  if (!total) return null
  return Math.round((top.reduce((s, [name, n]) => s + n * weightOf(mine.get(name)), 0) / total) * 100)
}

/** 프로필 직무 id → 공고 직무 유형 id. 같은 id가 있거나 job_type을 적은 것만 */
export function roleToJob(options: ProfileOptions | undefined, jobTypes: JobType[]): (role: string) => string | null {
  const ids = new Set(jobTypes.map((j) => j.id))
  const mapped = new Map((options?.roles ?? []).filter((r) => r.job_type).map((r) => [r.id, r.job_type!]))
  return (role) => mapped.get(role) ?? (ids.has(role) ? role : null)
}

/** 직무 유형별 내 경력 연수(직무 구간 기간) */
export function jobYears(p: Profile | null, toJob: (role: string) => string | null, today = new Date()): Map<string, number> {
  const out = new Map<string, number>()
  for (const c of p?.careers ?? []) {
    for (const r of c.roles) {
      const job = toJob(r.role)
      if (job) out.set(job, (out.get(job) ?? 0) + months(r.start, r.end, today) / 12)
    }
  }
  return out
}

/** 희망 직무를 공고 직무 유형으로(순서 유지, 겹치면 하나) */
export function targetJobs(p: Profile | null, toJob: (role: string) => string | null): string[] {
  return [...new Set((p?.targetRoles ?? []).map(toJob).filter((j): j is string => !!j))]
}

/** 직무 유형별 AI 매칭 평균 점수(매긴 공고만) */
export function matchAverages(postings: Posting[], matches: Map<string, Match>): Map<string, { avg: number; n: number }> {
  const sums = new Map<string, [number, number]>()
  for (const p of postings) {
    const m = matches.get(p.id)
    if (!m || m.kind !== 'ai' || !p.jobType) continue
    const [s, n] = sums.get(p.jobType) ?? [0, 0]
    sums.set(p.jobType, [s + m.score, n + 1])
  }
  return new Map([...sums.entries()].map(([k, [s, n]]) => [k, { avg: Math.round(s / n), n }]))
}

export type Quadrant = 'apply' | 'grow' | 'keep' | 'reduce'

export interface Position {
  id: string
  name: string
  short: string
  /** 지금 열린 공고(내 기업 구분) */
  open: number
  /** 7일 전보다 늘어난 공고. 7일치가 안 되면 null */
  change: number | null
  fit: number | null
  years: number
  match: { avg: number; n: number } | null
  /** 요구 스킬(공고 수 많은 순) */
  skills: [string, number][]
  /** 적합도를 셀 수 없는 직무(요구 스킬이 없음)는 null: 포지션 맵과 네 칸에 넣지 않는다 */
  quadrant: Quadrant | null
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  if (!s.length) return 0
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

/** 포지션 맵: 직무 유형마다 수요(열린 공고)와 스킬 적합도. 수요 기준선은 보이는 직무들의 가운데 값 */
export function positions(m: CareerMetrics, jobTypes: JobType[], ctypes: string[] | null, mine: Map<string, number>,
  years: Map<string, number>, matchAvg: Map<string, { avg: number; n: number }>): { list: Position[]; demandLine: number } {
  const list = jobTypes.filter((j) => j.direction !== false).map((j) => {
    const series = sumSeries(m, { jobs: [j.id], ctypes })
    const len = series.open.length
    const open = series.open[len - 1] ?? 0
    const skills = currentOf(m, { jobs: [j.id], ctypes }).skills
    return {
      id: j.id, name: j.name, short: j.short ?? j.name, open,
      change: len > 7 ? open - series.open[len - 8] : null,
      fit: skillFit(skills, mine), years: years.get(j.id) ?? 0, match: matchAvg.get(j.id) ?? null, skills,
      quadrant: null as Quadrant | null,
    }
  })
  // 기준선은 맵에 보이는(적합도가 있는) 직무들의 가운데 값
  const demandLine = median(list.filter((p) => p.fit !== null).map((p) => p.open))
  for (const p of list) {
    if (p.fit === null) continue
    const high = p.open >= demandLine
    const fits = p.fit >= FIT_LINE
    p.quadrant = high ? (fits ? 'apply' : 'grow') : (fits ? 'keep' : 'reduce')
  }
  return { list, demandLine }
}

/** 강점: 그 직무가 많이 요구하는데 내가 실무 이상으로 가진 스킬 */
export function strengths(skills: [string, number][], mine: Map<string, number>, n: number): string[] {
  return skills.filter(([name]) => (mine.get(name) ?? 0) >= FIT_LEVEL).slice(0, n).map(([name]) => name)
}

/** 채우면 좋은 것: 많이 요구하는데 없거나 써 본 정도인 스킬 */
export function gaps(skills: [string, number][], mine: Map<string, number>, n: number): { name: string; count: number; level: number }[] {
  return skills.filter(([name]) => (mine.get(name) ?? 0) < FIT_LEVEL).slice(0, n)
    .map(([name, count]) => ({ name, count, level: mine.get(name) ?? 0 }))
}

/** 다른 방향: 목표가 아닌 직무를 수요 × 적합도 순으로 */
export function otherDirections(list: Position[], targets: string[], n: number): Position[] {
  const max = Math.max(1, ...list.map((p) => p.open))
  return list.filter((p) => !targets.includes(p.id) && p.fit !== null)
    .sort((a, b) => (b.open / max) * (b.fit ?? 0) - (a.open / max) * (a.fit ?? 0))
    .slice(0, n)
}

/** 짧은 눈금: 0부터 max를 넘는 깔끔한 값까지. 공고 수라 간격은 1 이상(0.5 같은 눈금이 없게) */
export function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0]
  const raw = max / count
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = Math.max(1, [1, 2, 5, 10].map((k) => k * pow).find((s) => s >= raw) ?? 10 * pow)
  const out: number[] = []
  for (let v = 0; v < max + step; v += step) out.push(v)
  return out
}

/** 달력 주(월~일)마다 새 공고. from(첫날 제외)부터 끝(오늘)까지. 이번 주는 며칠째인지(days)도 */
export function weekBins(days: string[], values: (number | null)[], from: number): (Bin & { days: number })[] {
  const out: (Bin & { days: number })[] = []
  for (let i = from; i < days.length; i++) {
    const d = new Date(`${days[i]}T00:00:00`)
    const monday = new Date(d)
    monday.setDate(d.getDate() - ((d.getDay() + 6) % 7))
    const key = `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, '0')}-${String(monday.getDate()).padStart(2, '0')}`
    const last = out[out.length - 1]
    const v = values[i]
    if (last && last.start === key) {
      last.end = days[i]
      last.days += 1
      if (v !== null) last.value = (last.value ?? 0) + v
    } else {
      out.push({ start: key, end: days[i], value: v, days: 1 })
    }
  }
  return out
}

/** "10월 2주": 그 주 월요일이 그달 몇째 주인지 */
export function weekLabel(monday: string): string {
  const d = new Date(`${monday}T00:00:00`)
  return `${d.getMonth() + 1}월 ${Math.ceil(d.getDate() / 7)}주`
}
