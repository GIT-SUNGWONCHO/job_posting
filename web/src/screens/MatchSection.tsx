import { useState } from 'react'
import { copy } from '../copy'
import { DOWN_ICON, Score, SectionTitle } from '../components/ui'
import { saveFeedback, type Feedback } from '../lib/feedback'
import { matchKey, type Label, type Match, type MatchDetail } from '../lib/matches'

const t = copy.match
const FIT_CLASS: Record<string, string> = { 충족: 'fit good', 일부: 'fit part', 미충족: 'fit bad', '정보 없음': 'fit none' }
const LABELS: Label[] = ['good', 'maybe', 'bad']
/** 화면용 파일에 판정 비율이 없을 때(예전 파일) 쓰는 값. config/match_guide.yaml fit과 같다 */
const FIT_FALLBACK: Record<string, number> = { 충족: 1, 일부: 0.5, 미충족: 0, '정보 없음': 0.5 }

/** 판정: 진한 점수 상자 · 지원 추천 · 끝에 AI 의견, 아래 이유 두 줄(음영 없이) */
export function Verdict({ match }: { match: Match }) {
  return (
    <section className="section verdict-sec">
      <div className="verdict-head">
        <Score value={match.score} solid />
        {match.verdict && <span className="verdict-text">{match.verdict}</span>}
        {match.kind === 'ai' && <span className="ai-tag">{copy.job.aiOpinion}</span>}
      </div>
      {match.reason && <p className="verdict-reason">{match.reason}</p>}
      {match.kind === 'rule' && <p className="note">{t.ruleOnly}</p>}
    </section>
  )
}

/** 판단 근거: 항목마다 종류 · 이름 · 판정 · 받은 점수 / 배점. 누르면 공고 요구와 내 근거 */
export function Basis({ detail, fit }: { detail: MatchDetail; fit?: Record<string, number> }) {
  const [open, setOpen] = useState<number | null>(null)
  const ratio = fit ?? FIT_FALLBACK
  const items = [...detail.items].sort((a, b) => b.weight - a.weight)
  if (items.length === 0) return null
  return (
    <section className="section basis">
      <SectionTitle info={<>{t.basisHelp}<br />{t.meta(detail.rule, detail.model, detail.scoreV)}</>}>{t.basis}</SectionTitle>
      <div className="basis-list">
        {items.map((it, i) => {
          const got = Math.round(it.weight * (ratio[it.fit] ?? 0.5))
          const expanded = open === i
          const more = it.posting || it.me
          return (
            <div key={i} className="basis-item">
              <button type="button" className="basis-head" aria-expanded={more ? expanded : undefined} disabled={!more}
                onClick={() => setOpen(expanded ? null : i)}>
                <span className="basis-main"><span className="basis-kind">{it.kind}</span><span className="basis-name">{it.name}</span></span>
                <span className={FIT_CLASS[it.fit] ?? 'fit none'}>{it.fit}</span>
                <span className="basis-points"><b>{got}</b><span> / {it.weight}</span></span>
                {more ? <span className={expanded ? 'chev up' : 'chev'}>{DOWN_ICON}</span> : <span className="chev" />}
              </button>
              {expanded && (
                <div className="basis-detail">
                  {it.posting && <><span>{t.posting}</span><span>{it.posting}</span></>}
                  {it.me && <><span>{t.me}</span><span>{it.me}</span></>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

/** 내 평가(개발용: 매칭 기준을 만드는 정답). 점선 상자 */
export function MyRating({ postingId, posting, detail, feedback, onFeedback }: {
  postingId: string
  posting: { company: string; title: string }
  detail: MatchDetail
  feedback?: Feedback
  onFeedback: (postingId: string, f: Feedback) => void
}) {
  return (
    <div className="dev-box">
      <span className="dev-tag">{t.devTag}</span>
      <FeedbackBox key={`${postingId}:${matchKey(detail)}`} postingId={postingId} posting={posting} detail={detail} feedback={feedback} onFeedback={onFeedback} />
    </div>
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
  // 내 평가는 공고에 대한 판단이라 지난 회차 것을 미리 채운다(회차 리포트도 공고별 최신 평가를 정답으로 쓴다)
  const [label, setLabel] = useState<Label | null>(current?.label ?? feedback?.label ?? null)
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
      {feedback && !current && <p className="note">{t.previous}</p>}
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
