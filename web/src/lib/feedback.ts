import { supabase } from './supabase'
import { matchKey, type Label, type MatchDetail } from './matches'

// 매칭 결과에 남기는 내 평가(Supabase feedback 표, supabase/migrations/004_feedback.sql).
// 평가한 순간의 점수·판단 근거를 snapshot에 함께 저장한다. 같은 매칭 결과에는 한 줄(고치면 덮어씀).

export interface Feedback {
  label: Label
  comment: string
  matchKey: string
}

/** 공고마다 가장 최근 평가 */
export async function loadFeedback(): Promise<Map<string, Feedback>> {
  const out = new Map<string, Feedback>()
  if (!supabase) return out
  const { data, error } = await supabase.from('feedback').select('posting_id, label, comment, match_key').order('updated_at')
  if (error || !data) return out
  for (const r of data) {
    out.set(r.posting_id as string, { label: r.label as Label, comment: (r.comment as string | null) ?? '', matchKey: r.match_key as string })
  }
  return out
}

export async function saveFeedback(postingId: string, detail: MatchDetail, label: Label, comment: string,
  posting: { company: string; title: string }): Promise<Feedback | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getUser()
  if (!data.user) return null
  const key = matchKey(detail)
  const { error } = await supabase.from('feedback').upsert({
    user_id: data.user.id,
    posting_id: postingId,
    match_key: key,
    label,
    comment: comment.trim() || null,
    snapshot: {
      score: detail.score, verdict: detail.verdict, rule: detail.rule, reason: detail.reason, items: detail.items,
      missing: detail.missing, model: detail.model, guide: detail.scoreV, profile: detail.profileV, ...posting,
    },
    updated_at: new Date().toISOString(),
  })
  return error ? null : { label, comment, matchKey: key }
}
