import { supabase } from './supabase'

// 프로필(Supabase profiles 표, supabase/migrations/002_profiles.sql). 본인 행만 읽고 쓴다.
// AI에는 회사 이름 대신 업종을 보낸다(docs/decisions.md 2026-10-13 매칭).

export interface Job {
  company: string
  industry: string
  start: string // YYYY-MM
  end: string // YYYY-MM, 비우면 현재
  role: string
}

export interface Project {
  title: string
  result: string
}

export interface Profile {
  careerStart: string // YYYY-MM
  currentRole: string // 직무 유형 id
  targetRoles: string[]
  jobs: Job[]
  projects: Project[]
  skills: string[]
}

export const emptyProfile: Profile = {
  careerStart: '',
  currentRole: '',
  targetRoles: [],
  jobs: [],
  projects: [],
  skills: [],
}

export async function loadProfile(): Promise<{ profile: Profile; version: number } | null> {
  if (!supabase) return null
  const { data, error } = await supabase.from('profiles').select('data, version').maybeSingle()
  if (error || !data) return null
  return { profile: { ...emptyProfile, ...(data.data as Partial<Profile>) }, version: data.version as number }
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

/** 경력 시작 연월부터 오늘까지 햇수(반올림). "경력 약 N년"에 쓴다. */
export function careerYears(start: string, today = new Date()): number | null {
  const m = /^(\d{4})-(\d{2})$/.exec(start)
  if (!m) return null
  const months = (today.getFullYear() - Number(m[1])) * 12 + (today.getMonth() + 1 - Number(m[2]))
  return months < 0 ? null : Math.round(months / 12)
}
