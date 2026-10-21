import { readLocal, writeLocal } from './storage'
import { supabase } from './supabase'

// 할 일(Supabase plans 표, supabase/migrations/008_plans.sql). 커리어 탭 성장 계획의 "이번 달 할 일".
// Supabase가 없으면(개발) 이 기기에만 저장한다.

export type PlanKind = 'study' | 'project' | 'cert' | 'etc'
export const PLAN_KINDS: PlanKind[] = ['study', 'project', 'cert', 'etc']

export interface Plan {
  id: string
  /** YYYY-MM */
  month: string
  text: string
  kind: PlanKind
  /** "채우면 좋은 것"에서 넣었으면 그 스킬 */
  skill: string | null
  done: boolean
  createdAt: string
}

const LOCAL_KEY = 'jobpost.plans.v1'

/** 할 일 전부. 표가 아직 없으면(008을 실행하기 전) 'missing', 그 밖의 오류는 'failed' */
export async function loadPlans(): Promise<Plan[] | 'missing' | 'failed'> {
  if (!supabase) return readLocal<Plan[]>(LOCAL_KEY) ?? []
  const { data, error } = await supabase.from('plans').select('id, month, text, kind, skill, done, created_at')
    .order('created_at')
  // 42P01: Postgres 표 없음, PGRST205: PostgREST가 표를 찾지 못함
  if (error) return error.code === '42P01' || error.code === 'PGRST205' ? 'missing' : 'failed'
  if (!data) return 'failed'
  return data.map((r) => ({
    id: r.id as string, month: r.month as string, text: r.text as string, kind: r.kind as PlanKind,
    skill: (r.skill as string | null) ?? null, done: !!r.done, createdAt: r.created_at as string,
  }))
}

export async function savePlan(p: Plan): Promise<boolean> {
  if (!supabase) {
    const all = readLocal<Plan[]>(LOCAL_KEY) ?? []
    writeLocal(LOCAL_KEY, all.some((x) => x.id === p.id) ? all.map((x) => (x.id === p.id ? p : x)) : [...all, p])
    return true
  }
  const { data } = await supabase.auth.getUser()
  if (!data.user) return false
  const { error } = await supabase.from('plans').upsert({
    id: p.id, user_id: data.user.id, month: p.month, text: p.text.trim(), kind: p.kind, skill: p.skill, done: p.done,
    created_at: p.createdAt, updated_at: new Date().toISOString(),
  })
  return !error
}

export async function deletePlan(id: string): Promise<boolean> {
  if (!supabase) {
    writeLocal(LOCAL_KEY, (readLocal<Plan[]>(LOCAL_KEY) ?? []).filter((x) => x.id !== id))
    return true
  }
  const { error } = await supabase.from('plans').delete().eq('id', id)
  return !error
}

export function newPlan(month: string, text: string, kind: PlanKind, skill: string | null = null): Plan {
  return { id: crypto.randomUUID(), month, text: text.trim(), kind, skill, done: false, createdAt: new Date().toISOString() }
}

/** 이번 달 할 일과, 지난달까지 적고 아직 못 끝낸 할 일 */
export function monthView(plans: Plan[], month: string): { now: Plan[]; carried: Plan[] } {
  return {
    now: plans.filter((p) => p.month === month),
    carried: plans.filter((p) => p.month < month && !p.done),
  }
}
