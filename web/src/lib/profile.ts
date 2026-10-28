import { supabase } from './supabase'

// 프로필 v2(Supabase profiles 표). 형식과 계산은 src/jobpost/profile.py와 같다. 본인 행만 읽고 쓴다.
// 경력(회사) > 직무 구간 > 프로젝트. 직무가 바뀌면 직무 구간을 새 칸으로 적는다(비중 없음).
// AI에는 회사명까지 보내고 이름·연락처는 보내지 않는다(docs/decisions.md 2026-10-14 매칭).

export interface Project {
  title: string
  start: string // YYYY-MM
  end: string // 비우면 현재
  part: string // 단독 · 리드 · 참여
  summary: string
  skills: string[]
}

export interface Role {
  role: string // config/profile.yaml roles의 id
  roleName?: string // role이 other일 때 직접 쓴 이름
  start: string
  end: string
  summary: string
  projects: Project[]
}

export interface Career {
  company: string
  industry: string // config/profile.yaml industries의 id
  start: string
  end: string
  title: string // 직급
  roles: Role[]
}

export interface Skill {
  name: string
  level: number // 1~4, 0은 아직 안 고름
}

export interface Profile {
  schema: 2
  careers: Career[]
  targetRoles: string[]
  skills: Skill[]
  education: { degree: string; major: string; majorGroup: string }
  certs: { name: string; year: string }[]
  english: string
}

export const emptyProfile: Profile = {
  schema: 2,
  careers: [],
  targetRoles: [],
  skills: [],
  education: { degree: '', major: '', majorGroup: '' },
  certs: [],
  english: '',
}

export const emptyCareer = (): Career => ({ company: '', industry: '', start: '', end: '', title: '', roles: [] })
export const emptyRole = (): Role => ({ role: '', start: '', end: '', summary: '', projects: [] })
export const emptyProject = (): Project => ({ title: '', start: '', end: '', part: '', summary: '', skills: [] })

const NON_DATA_ROLES = new Set(['pi', 'sales_md'])

/** 예전(v1) 프로필을 v2 모양으로 옮긴다. 옮길 곳이 애매한 프로젝트는 가장 최근 경력 아래에 모은다 */
export function upgrade(data: Record<string, unknown>): Profile {
  if (data.schema === 2) return { ...emptyProfile, ...(data as Partial<Profile>) } as Profile
  const jobs = (data.jobs as { company: string; start: string; end: string; role: string }[] | undefined) ?? []
  const careers: Career[] = jobs.map((j) => ({ ...emptyCareer(), company: j.company, start: j.start, end: j.end,
    roles: j.role ? [{ ...emptyRole(), role: 'other', roleName: j.role, start: j.start, end: j.end }] : [] }))
  const projects = (data.projects as { title: string; result: string }[] | undefined) ?? []
  if (projects.length && careers.length) {
    const last = careers.reduce((a, b) => (b.start > a.start ? b : a))
    if (!last.roles.length) last.roles.push({ ...emptyRole(), role: 'other', roleName: '', start: last.start, end: last.end })
    last.roles[0].projects = projects.map((p) => ({ ...emptyProject(), title: p.title, summary: p.result }))
  }
  const skills = ((data.skills as string[] | undefined) ?? []).map((name) => ({ name, level: 0 }))
  return { ...emptyProfile, careers, skills, targetRoles: (data.targetRoles as string[] | undefined) ?? [] }
}

export async function loadProfile(): Promise<{ profile: Profile; version: number } | null> {
  if (!supabase) {
    // 개발할 때는 .dev-data/profile.json(있으면)
    if (!import.meta.env.DEV) return null
    const res = await fetch('/__dev/json/profile.json').catch(() => null)
    return res?.ok ? { profile: upgrade(await res.json()), version: 0 } : null
  }
  const { data, error } = await supabase.from('profiles').select('data, version').maybeSingle()
  if (error || !data) return null
  return { profile: upgrade((data.data ?? {}) as Record<string, unknown>), version: data.version as number }
}

export async function saveProfile(profile: Profile, version: number): Promise<boolean> {
  if (!supabase) return false
  const { data } = await supabase.auth.getUser()
  if (!data.user) return false
  const { error } = await supabase.from('profiles').upsert({
    user_id: data.user.id,
    data: profile,
    version,
    updated_at: new Date().toISOString(),
  })
  return !error
}

function monthIndex(s: string): number | null {
  const m = /^(\d{4})-(\d{2})$/.exec(s)
  return m ? Number(m[1]) * 12 + Number(m[2]) - 1 : null
}

/** 시작 달부터 끝 달까지(끝 달 포함). 끝이 비면 이번 달까지 */
export function months(start: string, end: string, today = new Date()): number {
  const a = monthIndex(start)
  const b = end ? monthIndex(end) : today.getFullYear() * 12 + today.getMonth()
  return a !== null && b !== null ? Math.max(0, b - a + 1) : 0
}

export function roleLabel(r: Role, names: Record<string, string>): string {
  return r.role === 'other' ? (r.roleName ?? '').trim() : names[r.role] ?? r.role
}

/** 직무 이름별 연수 */
export function roleYears(p: Profile, names: Record<string, string>, today = new Date()): [string, number][] {
  const out = new Map<string, number>()
  for (const c of p.careers) {
    if (!c.roles.length) out.set('직무 미입력', (out.get('직무 미입력') ?? 0) + months(c.start, c.end, today) / 12)
    for (const r of c.roles) {
      const name = roleLabel(r, names) || '직무 미입력'
      out.set(name, (out.get(name) ?? 0) + months(r.start, r.end, today) / 12)
    }
  }
  return [...out.entries()].sort((a, b) => b[1] - a[1])
}

/** [총 경력, 데이터·AI 경력] 연수. 데이터가 아닌 직무(PI 기획, 영업·MD)는 데이터 경력에서 뺀다 */
export function careerTotals(p: Profile, today = new Date()): [number, number] {
  const total = p.careers.reduce((s, c) => s + months(c.start, c.end, today), 0) / 12
  const nonData = p.careers.flatMap((c) => c.roles).filter((r) => NON_DATA_ROLES.has(r.role))
    .reduce((s, r) => s + months(r.start, r.end, today), 0) / 12
  return [total, Math.max(0, total - nonData)]
}

export const yearsText = (n: number) => n.toFixed(1).replace(/\.0$/, '')

/** 기간 표기: 2021.03 ~ 재직 중 (5년 8개월). 끝이 비면 nowLabel */
export function periodText(start: string, end: string, nowLabel: string, today = new Date()): string {
  const dot = (s: string) => s.replace('-', '.')
  const m = months(start, end, today)
  const span = m ? ` (${durationText(m)})` : ''
  return start ? `${dot(start)} ~ ${end ? dot(end) : nowLabel}${span}` : ''
}

/** 개월 수를 "5년 8개월" · "8개월" · "3년"으로 */
export function durationText(m: number): string {
  const y = Math.floor(m / 12)
  const r = m % 12
  return [y > 0 && `${y}년`, r > 0 && `${r}개월`].filter(Boolean).join(' ') || '0개월'
}
