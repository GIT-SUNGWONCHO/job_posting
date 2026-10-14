import { useEffect, useState } from 'react'
import { copy } from '../copy'
import { Score } from '../components/ui'
import { saveFeedback, type Feedback } from '../lib/feedback'
import { loadMatchDetail, matchKey, type Label, type MatchDetail } from '../lib/matches'

const t = copy.match
const FIT_CLASS: Record<string, string> = { 충족: 'fit good', 일부: 'fit part', 미충족: 'fit bad', '정보 없음': 'fit none' }
const LABELS: Label[] = ['good', 'maybe', 'bad']

// 공고 상세의 매칭: 점수, AI 판정과 이유, 판단 근거(항목 · 공고 요구 · 내 근거 · 판정 · 가중치), 내 평가
export function MatchSection({ postingId, posting, feedback, onFeedback }: {
  postingId: string
  posting: { company: string; title: string }
  feedback?: Feedback
  onFeedback: (postingId: string, f: Feedback) => void
}) {
  const [detail, setDetail] = useState<{ id: string; d: MatchDetail | null } | null>(null)
  useEffect(() => {
    let alive = true
    loadMatchDetail(postingId).then((d) => alive && setDetail({ id: postingId, d }), () => alive && setDetail({ id: postingId, d: null }))
    return () => {
      alive = false
    }
  }, [postingId])

  const d = detail?.id === postingId ? detail.d : null
  if (!d) return null
  const items = [...d.items].sort((a, b) => b.weight - a.weight)
  return (
    <section className="section">
      <div className="match-head">
        <Score value={d.score} solid size={56} />
        <div className="row-main">
          {d.verdict && <span className="verdict">{d.verdict}</span>}
          {d.reason && <span className="match-reason">{d.reason} <span className="badge-ai">{copy.job.aiOpinion}</span></span>}
          {d.kind === 'rule' && <span className="note">{t.ruleOnly}</span>}
        </div>
      </div>
      {items.length > 0 && (
        <div className="basis">
          <div className="basis-title">
            <h3>{t.basis}</h3>
            <span className="count">{t.basisHelp}</span>
          </div>
          {items.map((it, i) => (
            <div key={i} className="basis-item">
              <div className="basis-head">
                <span className="basis-kind">{it.kind}</span>
                <span className="basis-name">{it.name}</span>
                <span className={FIT_CLASS[it.fit] ?? 'fit none'}>{it.fit}</span>
                <span className="basis-weight" aria-label={t.weight}>{it.weight}</span>
              </div>
              {it.posting && <div className="basis-line"><span>{t.posting}</span>{it.posting}</div>}
              {it.me && <div className="basis-line"><span>{t.me}</span>{it.me}</div>}
            </div>
          ))}
        </div>
      )}
      {d.missing.length > 0 && (
        <div className="skill-line"><span>{copy.job.gap}</span>
          <div className="chips wrap small">{d.missing.map((s) => <span key={s} className="chip gap">{s}</span>)}</div>
        </div>
      )}
      <p className="note basis-meta">{t.meta(d.rule, d.model, d.scoreV)}</p>
      <FeedbackBox key={`${postingId}:${matchKey(d)}`} postingId={postingId} posting={posting} detail={d} feedback={feedback} onFeedback={onFeedback} />
    </section>
  )
}

function FeedbackBox({ postingId, posting, detail, feedback, onFeedback }: {
  postingId: string
  posting: { company: string; title: string }
  detail: MatchDetail
  feedback?: Feedback
  onFeedback: (postingId: string, f: Feedback) => void
}) {
  const current = feedback?.matchKey === matchKey(detail) ? feedback : undefined
  const [label, setLabel] = useState<Label | null>(current?.label ?? null)
  const [comment, setComment] = useState(current?.comment ?? '')
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>(current ? 'saved' : 'idle')

  async function save() {
    if (!label) return
    setState('saving')
    const f = await saveFeedback(postingId, detail, label, comment, posting)
    if (f) onFeedback(postingId, f)
    setState(f ? 'saved' : 'failed')
  }
  const changed = () => state !== 'idle' && state !== 'saving' && setState('idle')

  return (
    <div className="feedback">
      <h3>{t.mine}</h3>
      {feedback && !current && <p className="note">{t.previous(t.labels[feedback.label])}</p>}
      <div className="chips wrap" role="radiogroup" aria-label={t.mine}>
        {LABELS.map((l) => (
          <button key={l} type="button" role="radio" aria-checked={label === l} className={label === l ? 'chip selected' : 'chip'}
            onClick={() => { setLabel(l); changed() }}>{t.labels[l]}</button>
        ))}
      </div>
      <textarea rows={3} value={comment} placeholder={t.commentPlaceholder} aria-label={t.comment}
        onChange={(e) => { setComment(e.target.value); changed() }} />
      <div className="feedback-actions">
        {state === 'saved' && <span className="note">{t.saved}</span>}
        {state === 'failed' && <span className="note urgent">{t.failed}</span>}
        <button type="button" className="btn primary" disabled={!label || state === 'saving'} onClick={save}>{t.save}</button>
      </div>
    </div>
  )
}
