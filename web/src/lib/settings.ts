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
