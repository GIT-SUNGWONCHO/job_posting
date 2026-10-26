import { supabase } from './supabase'
import type { Filters } from './types'

// 사람별 설정(Supabase settings 표, supabase/migrations/001_settings.sql). 본인 행만 읽고 쓴다.

/** 계정에 저장된 필터. 아직 없으면 null. Supabase가 없으면(개발) 늘 null. */
export async function loadFilters(): Promise<Filters | null> {
  if (!supabase) return null
  const { data, error } = await supabase.from('settings').select('filters').maybeSingle()
  if (error || !data) return null
  return data.filters as Filters
}

export async function saveFilters(filters: Filters): Promise<boolean> {
  if (!supabase) return false
  const { data } = await supabase.auth.getUser()
  if (!data.user) return false
  const { error } = await supabase
    .from('settings')
    .upsert({ user_id: data.user.id, filters, updated_at: new Date().toISOString() })
  return !error
}

/** 아침 알림 설정(settings.notify, supabase/migrations/010_notify_settings.sql). 고르지 않은 값은 config/notify.yaml 기본값.
 * 매일 작업은 src/jobpost/notify.py prefs_of로 읽는다 */
export interface NotifyPrefs {
  enabled?: boolean
  top?: number
  soon_min_score?: number
}

/** 010을 실행하기 전이면 'missing', 그 밖의 오류는 'failed'. 42703: 칸 없음, PGRST204: PostgREST가 칸을 찾지 못함 */
export type Loaded<T> = T | 'missing' | 'failed'
const missing = (code: string | undefined) => code === '42703' || code === 'PGRST204' || code === '42501'

export async function loadNotify(): Promise<Loaded<NotifyPrefs>> {
  if (!supabase) return {}
  const { data, error } = await supabase.from('settings').select('notify').maybeSingle()
  if (error) return missing(error.code) ? 'missing' : 'failed'
  return (data?.notify as NotifyPrefs | undefined) ?? {}
}

export async function saveNotify(prefs: NotifyPrefs): Promise<boolean> {
  if (!supabase) return false
  const { data } = await supabase.auth.getUser()
  if (!data.user) return false
  const { error } = await supabase
    .from('settings')
    .upsert({ user_id: data.user.id, notify: prefs, updated_at: new Date().toISOString() })
  return !error
}

/** 텔레그램 알림 연결: 연결했으면 마지막으로 보낸 날(아직 안 보냈으면 null), 연결 안 했으면 undefined */
export interface TelegramLink {
  lastSentOn: string | null
  updatedAt: string
}

export async function loadTelegramLink(): Promise<Loaded<TelegramLink | null>> {
  if (!supabase) return null
  const { data, error } = await supabase.from('telegram_links').select('last_sent_on, updated_at').maybeSingle()
  if (error) return missing(error.code) ? 'missing' : 'failed'
  return data ? { lastSentOn: data.last_sent_on as string | null, updatedAt: data.updated_at as string } : null
}
