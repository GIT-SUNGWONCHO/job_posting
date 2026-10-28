import { supabase } from './supabase'

// 내 리서치 노트(Supabase research_notes, 본인 줄만). 노트는 정해진 블록으로만 쓰고 화면이 그린다.
// 형식은 src/jobpost/notes.py(넣기 전 확인)와 docs/content-rules.md "내 리서치 노트"와 같다.

export type NoteBlock = { title?: string } & (
  | { t: 'kv'; rows: [string, string, string?][] }
  | { t: 'sub'; text: string }
  | { t: 'facts'; items: string[] }
  | { t: 'table'; head?: string[]; rows: string[][]; strong?: number }
  | { t: 'timeline'; items: [string, string, string?][] }
  | { t: 'stack'; series: [string, string]; unit: '억'; rows: [string, number, number][]; on?: string }
  | { t: 'mix'; series: string[]; rows: (string | number)[][] }
  | { t: 'steps'; items: [string, string, string][] }
  | { t: 'quote'; text: string; by: string }
  | { t: 'path'; items: string[]; note?: string }
  | { t: 'cards'; items: [string, string, boolean?][] }
)

export interface NoteSection {
  title: string
  blocks: NoteBlock[]
  sources: { title: string; url?: string | null }[]
}

export interface Note {
  v: number
  company: string
  name: string
  /** 마지막으로 고친 날(YYYY-MM-DD) */
  updated: string
  /** 노트를 쓴 기준 공고(있으면) */
  posting?: { title: string; deadline?: string | null; url?: string | null; id?: string | null }
  summary: string[]
  sections: NoteSection[]
}

/** 회사 하나의 노트. 없거나 못 읽으면 null(표가 아직 없을 때도) */
export async function loadNote(companyKey: string): Promise<Note | null> {
  if (supabase) {
    const res = await supabase.from('research_notes').select('note').eq('company_key', companyKey).maybeSingle()
    return res.error || !res.data ? null : (res.data.note as Note)
  }
  if (import.meta.env.DEV) {
    // 개발할 때는 .dev-data/notes/<회사 키>.json(있으면)
    const res = await fetch(`/__dev/notes/${encodeURIComponent(companyKey)}.json`).catch(() => null)
    return res?.ok ? res.json() : null
  }
  return null
}
