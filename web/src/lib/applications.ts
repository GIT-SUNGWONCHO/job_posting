import { createContext, useContext } from 'react'
import { readLocal, writeLocal } from './storage'
import { supabase } from './supabase'
import type { DeadlineType, Posting } from './types'

// 지원 상태(Supabase applications 표, supabase/migrations/007_applications.sql). 단계 이름은 용어집 "지원 단계".
// 공고가 마감돼 화면용 파일에서 빠져도 보이게 회사·제목·주소·마감을 snapshot에 함께 저장한다.
// Supabase가 없으면(개발) 이 기기에만 저장한다.

export type Stage = 'interest' | 'applied' | 'passed' | 'interview' | 'result' | 'dismissed'
export type Outcome = 'pass' | 'fail'

/** 지원 현황의 단계 순서(관심 없음은 따로) */
export const STAGES: Stage[] = ['interest', 'applied', 'passed', 'interview', 'result']
/** 다시 추천하지 않는 단계: 이미 지원했거나 관심 없음 */
export const NOT_AGAIN: Stage[] = ['applied', 'passed', 'interview', 'result', 'dismissed']

export interface Snapshot {
  company: string
  title: string
  url: string | null
  deadlineType: DeadlineType
  deadline: string | null
}

export interface Application {
  postingId: string
  stage: Stage
  outcome: Outcome | null
  memo: string
  nextOn: string | null
  nextLabel: string
  /** 단계마다 처음 고른 날(YYYY-MM-DD) */
  dates: Partial<Record<Stage, string>>
  snapshot: Snapshot
}

const LOCAL_KEY = 'jobpost.applications.v1'

/** 화면 어디서나(목록 줄의 단계 표시, 리포트에서 빼기) 내 지원 상태를 읽는다. App이 채운다 */
export const AppsContext = createContext<Map<string, Application>>(new Map())
export const useApps = () => useContext(AppsContext)

export function snapshotOf(p: Posting, companyName: string): Snapshot {
  return {
    company: companyName, title: p.title, url: p.sources.find((s) => s.url)?.url ?? null,
    deadlineType: p.deadlineType, deadline: p.deadline,
  }
}

export async function loadApplications(): Promise<Map<string, Application>> {
  const out = new Map<string, Application>()
  if (!supabase) {
    for (const a of readLocal<Application[]>(LOCAL_KEY) ?? []) out.set(a.postingId, a)
    return out
  }
  const { data, error } = await supabase.from('applications')
    .select('posting_id, stage, outcome, memo, next_on, next_label, dates, snapshot')
  if (error || !data) return out
  for (const r of data) {
    out.set(r.posting_id as string, {
      postingId: r.posting_id as string, stage: r.stage as Stage, outcome: (r.outcome as Outcome | null) ?? null,
      memo: (r.memo as string | null) ?? '', nextOn: (r.next_on as string | null) ?? null,
      nextLabel: (r.next_label as string | null) ?? '', dates: (r.dates as Application['dates']) ?? {},
      snapshot: r.snapshot as Snapshot,
    })
  }
  return out
}

/** 저장하고 성공하면 true. 단계가 처음이면 오늘 날짜를 남긴다. */
export async function saveApplication(a: Application, today: string): Promise<boolean> {
  const dates = a.dates[a.stage] ? a.dates : { ...a.dates, [a.stage]: today }
  const row = { ...a, dates }
  if (!supabase) {
    const all = (readLocal<Application[]>(LOCAL_KEY) ?? []).filter((x) => x.postingId !== a.postingId)
    writeLocal(LOCAL_KEY, [...all, row])
    return true
  }
  const { data } = await supabase.auth.getUser()
  if (!data.user) return false
  const { error } = await supabase.from('applications').upsert({
    user_id: data.user.id, posting_id: a.postingId, stage: a.stage, outcome: a.stage === 'result' ? a.outcome : null,
    memo: a.memo.trim() || null, next_on: a.nextOn || null, next_label: a.nextLabel.trim() || null,
    dates, snapshot: a.snapshot, updated_at: new Date().toISOString(),
  })
  return !error
}

export async function deleteApplication(postingId: string): Promise<boolean> {
  if (!supabase) {
    writeLocal(LOCAL_KEY, (readLocal<Application[]>(LOCAL_KEY) ?? []).filter((x) => x.postingId !== postingId))
    return true
  }
  const { error } = await supabase.from('applications').delete().eq('posting_id', postingId)
  return !error
}

/** 다가오는 일정: 관심 공고의 마감(오늘부터 limitDays일 안)과 내가 적은 다음 일정(오늘부터). 날짜 순. */
export function upcoming(apps: Iterable<Application>, today: string, limitDays = 14):
  { date: string; postingId: string; company: string; what: 'deadline' | 'next'; label: string }[] {
  const end = new Date(Date.parse(today) + limitDays * 86400000).toISOString().slice(0, 10)
  const out: { date: string; postingId: string; company: string; what: 'deadline' | 'next'; label: string }[] = []
  for (const a of apps) {
    const s = a.snapshot
    // 마감은 아직 지원하지 않은 관심 공고만(지원한 뒤에는 마감이 의미 없다)
    if (a.stage === 'interest' && s.deadlineType === 'date' && s.deadline
      && s.deadline.slice(0, 10) >= today && s.deadline.slice(0, 10) <= end) {
      out.push({ date: s.deadline.slice(0, 10), postingId: a.postingId, company: s.company, what: 'deadline', label: '' })
    }
    if (a.nextOn && a.nextOn >= today && a.stage !== 'dismissed') {
      out.push({ date: a.nextOn, postingId: a.postingId, company: s.company, what: 'next', label: a.nextLabel })
    }
  }
  return out.sort((x, y) => x.date.localeCompare(y.date) || x.company.localeCompare(y.company))
}
