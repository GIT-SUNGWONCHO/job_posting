import { supabase } from './supabase'

// 매칭 결과(Supabase matches 표, 매일 수집 뒤 다시 계산). 본인 행만 읽는다.
export interface Match {
  score: number
  parts: { job: number; career: number; skills: number }
  matched: string[]
  missing: string[]
  /** AI 의견. 점수 상위 공고에만 있다 */
  reason: string | null
}

async function rows(): Promise<Record<string, unknown>[] | null> {
  if (supabase) {
    const { data, error } = await supabase.from('matches').select('posting_id, score, parts, matched, missing, reason')
    return error ? null : data
  }
  if (import.meta.env.DEV) {
    // 개발할 때는 .dev-data/matches.json(있으면)
    const res = await fetch('/__dev/matches.json').catch(() => null)
    return res?.ok ? res.json() : null
  }
  return null
}

export async function loadMatches(): Promise<Map<string, Match>> {
  const out = new Map<string, Match>()
  const data = await rows()
  if (!data) return out
  for (const r of data) {
    out.set(r.posting_id as string, {
      score: r.score as number,
      parts: r.parts as Match['parts'],
      matched: (r.matched as string[]) ?? [],
      missing: (r.missing as string[]) ?? [],
      reason: (r.reason as string | null) ?? null,
    })
  }
  return out
}
