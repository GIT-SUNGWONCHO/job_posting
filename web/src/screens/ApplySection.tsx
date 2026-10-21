import { useState } from 'react'
import { copy } from '../copy'
import { dateText } from '../lib/format'
import {
  deleteApplication, saveApplication, snapshotOf, STAGES, type Application, type Outcome, type Stage,
} from '../lib/applications'
import type { Posting } from '../lib/types'

const t = copy.apply
const CHOICES: Stage[] = [...STAGES, 'dismissed']

// 공고 상세의 지원 상태: 단계 고르기(누르면 바로 저장), 결과(합격·불합격), 메모·다음 일정(저장 버튼)
export function ApplySection({ posting, company, app, today, onChange }: {
  posting: Posting
  company: string
  app: Application | undefined
  today: string
  onChange: (postingId: string, app: Application | null) => void
}) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')

  async function save(next: Application) {
    setState('saving')
    const ok = await saveApplication(next, today)
    if (ok) onChange(posting.id, { ...next, dates: next.dates[next.stage] ? next.dates : { ...next.dates, [next.stage]: today } })
    setState(ok ? 'saved' : 'failed')
  }

  function pick(stage: Stage) {
    if (app?.stage === stage) return
    const base: Application = app ?? {
      postingId: posting.id, stage, outcome: null, memo: '', nextOn: null, nextLabel: '', dates: {},
      snapshot: snapshotOf(posting, company),
    }
    // 공고가 아직 열려 있으면 마감 같은 정보를 최신으로 바꿔 둔다
    save({ ...base, stage, snapshot: snapshotOf(posting, company) })
  }

  async function clear() {
    setState('saving')
    const ok = await deleteApplication(posting.id)
    if (ok) onChange(posting.id, null)
    setState(ok ? 'idle' : 'failed')
  }

  return (
    <section className="section apply">
      <h2>{t.status}</h2>
      <div className="chips wrap" role="radiogroup" aria-label={t.status}>
        {CHOICES.map((s) => (
          <button key={s} type="button" role="radio" aria-checked={app?.stage === s}
            className={app?.stage === s ? 'chip selected' : 'chip'} onClick={() => pick(s)}>{t.long[s]}</button>
        ))}
      </div>
      {app && <ApplyDetails key={app.postingId + app.stage} app={app} save={save} clear={clear} state={state} setState={setState} />}
      {!app && state === 'failed' && <span className="note urgent">{t.failed}</span>}
    </section>
  )
}

function ApplyDetails({ app, save, clear, state, setState }: {
  app: Application
  save: (a: Application) => void
  clear: () => void
  state: 'idle' | 'saving' | 'saved' | 'failed'
  setState: (s: 'idle' | 'saving' | 'saved' | 'failed') => void
}) {
  const [memo, setMemo] = useState(app.memo)
  const [nextOn, setNextOn] = useState(app.nextOn ?? '')
  const [nextLabel, setNextLabel] = useState(app.nextLabel)
  const since = app.dates[app.stage]
  const edited = () => state !== 'idle' && state !== 'saving' && setState('idle')

  return (
    <div className="apply-details">
      {since && <p className="note">{t.since(dateText(since, true))}{app.stage === 'dismissed' && ` · ${t.dismissedNote}`}</p>}
      {app.stage === 'result' && (
        <div className="chips wrap" role="radiogroup" aria-label={t.long.result}>
          {(['pass', 'fail'] as Outcome[]).map((o) => (
            <button key={o} type="button" role="radio" aria-checked={app.outcome === o}
              className={app.outcome === o ? 'chip selected' : 'chip'}
              onClick={() => save({ ...app, outcome: o })}>{t.outcomes[o]}</button>
          ))}
        </div>
      )}
      {app.stage !== 'dismissed' && (
        <>
          <label className="field">
            <span>{t.memo}</span>
            <textarea rows={3} value={memo} placeholder={t.memoPlaceholder}
              onChange={(e) => { setMemo(e.target.value); edited() }} />
          </label>
          <div className="row2">
            <label className="field">
              <span>{t.next}</span>
              <input type="date" value={nextOn} onChange={(e) => { setNextOn(e.target.value); edited() }} />
            </label>
            <label className="field">
              <span>{t.nextLabel}</span>
              <input value={nextLabel} placeholder={t.nextLabelPlaceholder}
                onChange={(e) => { setNextLabel(e.target.value); edited() }} />
            </label>
          </div>
        </>
      )}
      <div className="feedback-actions">
        <button type="button" className="text-link danger" onClick={clear}>{t.clear}</button>
        {state === 'saved' && <span className="note">{t.saved}</span>}
        {state === 'failed' && <span className="note urgent">{t.failed}</span>}
        {app.stage !== 'dismissed' && (
          <button type="button" className="btn primary" disabled={state === 'saving'}
            onClick={() => save({ ...app, memo, nextOn: nextOn || null, nextLabel })}>{t.save}</button>
        )}
      </div>
    </div>
  )
}
