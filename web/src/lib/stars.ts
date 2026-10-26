import { createContext, useContext } from 'react'
import { readLocal, writeLocal } from './storage'
import { supabase } from './supabase'

// 관심 회사(★). Supabase company_stars 표(supabase/migrations/009_company_stars.sql), 본인 줄만 읽고 쓴다.
// Supabase가 없으면(개발) 이 기기에만 저장한다.

const LOCAL_KEY = 'jobpost.stars.v1'

/** 회사 키 모음. 표가 아직 없으면(009를 실행하기 전) 'missing', 그 밖의 오류는 'failed', 불러오기 전은 undefined */
export type StarsState = Set<string> | 'missing' | 'failed' | undefined

export async function loadStars(): Promise<Exclude<StarsState, undefined>> {
  if (!supabase) return new Set(readLocal<string[]>(LOCAL_KEY) ?? [])
  const { data, error } = await supabase.from('company_stars').select('company_key')
  // 42P01: Postgres 표 없음, PGRST205: PostgREST가 표를 찾지 못함
  if (error) return error.code === '42P01' || error.code === 'PGRST205' ? 'missing' : 'failed'
  return new Set((data ?? []).map((r) => r.company_key as string))
}

/** ★를 켜거나 끈다. 저장되면 true. 켜기는 insert만 쓴다(upsert는 UPDATE 권한이 필요하다). 이미 있으면(23505) 성공 */
export async function saveStar(key: string, on: boolean): Promise<boolean> {
  if (!supabase) {
    const keys = new Set(readLocal<string[]>(LOCAL_KEY) ?? [])
    if (on) keys.add(key)
    else keys.delete(key)
    writeLocal(LOCAL_KEY, [...keys])
    return true
  }
  if (!on) {
    const { error } = await supabase.from('company_stars').delete().eq('company_key', key)
    return !error
  }
  const { error } = await supabase.from('company_stars').insert({ company_key: key })  // user_id는 표 기본값 auth.uid()
  return !error || error.code === '23505'
}

export interface Stars {
  state: StarsState
  /** 화면을 먼저 바꾸고 저장에 실패하면 되돌린다 */
  toggle: (key: string) => void
}

/** 회사 화면의 ★와 회사 목록의 관심 회사 칩이 함께 읽는다. App이 채운다 */
export const StarsContext = createContext<Stars>({ state: undefined, toggle: () => {} })
export const useStars = () => useContext(StarsContext)
export const isStarred = (state: StarsState, key: string) => state instanceof Set && state.has(key)
