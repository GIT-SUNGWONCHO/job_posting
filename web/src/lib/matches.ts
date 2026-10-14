import { supabase } from './supabase'

// 매칭 결과(Supabase matches 표, 매일 수집 뒤와 match 실행 때 다시 씀). 본인 행만 읽는다.
// 지금은 후보 공고를 AI가 항목별로 매기고 판단 근거를 남긴다(src/jobpost/recommend.py).
// 목록에는 점수·이유·판정만 받고, 판단 근거는 공고 상세를 열 때 그 공고만 받는다.

export type Label = 'good' | 'maybe' | 'bad'

export interface Match {
  score: number
  /** AI 의견 한 줄 */
  reason: string | null
  /** 지원 추천 · 고려 · 비추천(AI가 매겼을 때만) */
  verdict: string | null
  kind: 'ai' | 'rule'
  /** 내 평가(피드백) */
  mine?: Label
}

export interface MatchItem {
  kind: string
  name: string
  posting: string
  me: string
  fit: string
  weight: number
}

export interface MatchDetail extends Match {
  items: MatchItem[]
  /** 같은 공고의 규칙 점수(비교용) */
  rule: number | null
  matched: string[]
  missing: string[]
  model: string | null
  scoreV: number
  profileV: number
}

/** 피드백을 어느 매칭 결과에 단 것인지: 지침 버전 · 프로필 버전 · 모델 */
export const matchKey = (d: MatchDetail) => `g${d.scoreV}-p${d.profileV}-${d.model ?? 'rule'}`

type Row = Record<string, unknown>

async function devRows(): Promise<Row[] | null> {
  // 개발할 때는 .dev-data/matches.json(있으면)
  const res = await fetch('/__dev/json/matches.json').catch(() => null)
  return res?.ok ? res.json() : null
}

export async function loadMatches(): Promise<Map<string, Match>> {
  const out = new Map<string, Match>()
  let data: Row[] | null = null
  if (supabase) {
    const res = await supabase.from('matches').select('posting_id, score, reason, verdict:parts->>verdict, kind:parts->>kind')
    data = res.error ? null : res.data
  } else if (import.meta.env.DEV) {
    data = (await devRows())?.map((r) => ({ ...r, verdict: (r.parts as Row | null)?.verdict, kind: (r.parts as Row | null)?.kind })) ?? null
  }
  for (const r of data ?? []) {
    out.set(r.posting_id as string, {
      score: r.score as number,
      reason: (r.reason as string | null) ?? null,
      verdict: (r.verdict as string | null) ?? null,
      kind: r.kind === 'ai' ? 'ai' : 'rule',
    })
  }
  return out
}

export async function loadMatchDetail(postingId: string): Promise<MatchDetail | null> {
  let r: Row | null = null
  if (supabase) {
    const res = await supabase.from('matches')
      .select('score, parts, matched, missing, reason, reason_meta, score_v, profile_v').eq('posting_id', postingId).maybeSingle()
    r = res.error ? null : res.data
  } else if (import.meta.env.DEV) {
    r = (await devRows())?.find((x) => x.posting_id === postingId) ?? null
  }
  if (!r) return null
  const parts = (r.parts ?? {}) as Row
  const meta = (r.reason_meta ?? {}) as Row
  return {
    score: r.score as number,
    reason: (r.reason as string | null) ?? null,
    verdict: (parts.verdict as string | null) ?? null,
    kind: parts.kind === 'ai' ? 'ai' : 'rule',
    items: (parts.items as MatchItem[] | undefined) ?? [],
    rule: (parts.rule as number | undefined) ?? null,
    matched: (r.matched as string[]) ?? [],
    missing: (r.missing as string[]) ?? [],
    model: (meta.model as string | null) ?? null,
    scoreV: r.score_v as number,
    profileV: r.profile_v as number,
  }
}
