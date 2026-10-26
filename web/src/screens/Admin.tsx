import { useEffect, useState } from 'react'
import { copy } from '../copy'
import { SectionTitle } from '../components/ui'
import { dateText } from '../lib/format'
import { href } from '../lib/route'
import { loadNotify, loadTelegramLink, saveNotify, type Loaded, type NotifyPrefs, type TelegramLink } from '../lib/settings'
import { supabase } from '../lib/supabase'
import type { Collection, NotifyDefaults, Screen } from '../lib/types'

// 관리 탭: 프로필·이력서 메뉴, 아침 알림(연결 상태·설정), 수집 현황, 로그인 계정
export function Admin({ screen, today }: { screen: Screen; today: string }) {
  const [email, setEmail] = useState<string | null>(null)
  useEffect(() => {
    supabase?.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null))
  }, [])

  return (
    <div className="page">
      <header className="page-head"><h1>{copy.tabs.admin}</h1></header>
      <nav className="menu">
        <a className="menu-row" href={href.profile}>{copy.admin.profile}<span aria-hidden="true">›</span></a>
      </nav>
      {supabase && screen.notify && <NotifySettings defaults={screen.notify} />}
      <CollectionStatus run={screen.collection ?? null} today={today} />
      {supabase && (
        <section className="section">
          <SectionTitle>{copy.admin.account}</SectionTitle>
          <div className="account">
            <span>{email ?? ''}</span>
            <button type="button" className="btn" onClick={() => supabase?.auth.signOut()}>{copy.admin.logout}</button>
          </div>
        </section>
      )}
    </div>
  )
}

/** 아침 알림: 연결 상태와 사람별 설정(settings.notify). 고르면 바로 저장한다 */
function NotifySettings({ defaults }: { defaults: NotifyDefaults }) {
  const [prefs, setPrefs] = useState<Loaded<NotifyPrefs> | undefined>(undefined)
  const [link, setLink] = useState<Loaded<TelegramLink | null> | undefined>(undefined)
  const [saved, setSaved] = useState<'ok' | 'failed' | null>(null)
  useEffect(() => {
    let alive = true
    loadNotify().then((p) => alive && setPrefs(p))
    loadTelegramLink().then((l) => alive && setLink(l))
    return () => {
      alive = false
    }
  }, [])

  const editable = typeof prefs === 'object'
  const cur = editable ? prefs : {}
  const enabled = cur.enabled !== false
  const top = cur.top && defaults.choices.top.includes(cur.top) ? cur.top : defaults.top
  const score = cur.soon_min_score !== undefined && defaults.choices.soonMinScore.includes(cur.soon_min_score)
    ? cur.soon_min_score : defaults.soonMinScore

  function change(next: NotifyPrefs) {
    if (!editable) return
    const before = prefs
    const merged = { ...prefs, ...next }
    setPrefs(merged)
    setSaved(null)
    // 실패하면 고르기 전 값으로 되돌린다
    saveNotify(merged).then((ok) => {
      setSaved(ok ? 'ok' : 'failed')
      if (!ok) setPrefs(before)
    })
  }

  let status
  if (link === undefined) status = null
  else if (link === 'missing') status = <p className="note">{copy.admin.linkMissing}</p>
  else if (link === 'failed') status = <p className="note">{copy.admin.loadFailed}</p>
  else if (link) status = <p className="note"><span className="status-dot on" />{copy.admin.linked(link.lastSentOn ? dateText(link.lastSentOn) : null)}</p>
  else status = <p className="note"><span className="status-dot" />{copy.admin.notLinked}</p>

  return (
    <section className="section">
      <SectionTitle>{copy.admin.notify}</SectionTitle>
      <div className="admin-block">
        <p className="note">{copy.admin.when}</p>
        {status}
        {prefs === 'missing' && <p className="note">{copy.admin.prefsMissing}</p>}
        {prefs === 'failed' && <p className="note">{copy.admin.loadFailed}</p>}
        <label className="switch">
          {copy.admin.enabled}
          <input type="checkbox" checked={enabled} disabled={!editable} onChange={(e) => change({ enabled: e.target.checked })} />
        </label>
        <div className="row2">
          <label className="field">
            <span>{copy.admin.top}</span>
            <select value={top} disabled={!editable || !enabled} onChange={(e) => change({ top: Number(e.target.value) })}>
              {defaults.choices.top.map((n) => (
                <option key={n} value={n}>{copy.admin.topOption(n)}{n === defaults.top ? copy.admin.defaultMark : ''}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{copy.admin.soonScore}</span>
            <select value={score} disabled={!editable || !enabled} onChange={(e) => change({ soon_min_score: Number(e.target.value) })}>
              {defaults.choices.soonMinScore.map((n) => (
                <option key={n} value={n}>{copy.admin.scoreOption(n)}{n === defaults.soonMinScore ? copy.admin.defaultMark : ''}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="note small">{copy.admin.prefsNote}</p>
        {saved && <p className={saved === 'ok' ? 'note' : 'note urgent'} role="status">{saved === 'ok' ? copy.admin.saved : copy.admin.saveFailed}</p>}
      </div>
    </section>
  )
}

/** 수집 현황: 마지막 수집(data 브랜치 runs/)의 수집처별 받은 공고 수와 끝까지 받았는지 */
function CollectionStatus({ run, today }: { run: Collection | null; today: string }) {
  return (
    <section className="section">
      <SectionTitle>{copy.admin.collection}</SectionTitle>
      {!run ? (
        <p className="note">{copy.admin.noCollection}</p>
      ) : (
        <div className="admin-block">
          <p className="note">
            {copy.admin.lastRun(dateText(run.date), run.finished?.slice(11, 16) ?? '')}
            {run.new !== null && run.closed !== null && <> · {copy.admin.runCounts(run.new, run.closed)}</>}
          </p>
          {run.date < today && <p className="note urgent">{copy.admin.notToday}</p>}
          <div className="source-rows">
            {run.sources.map((s) => (
              <div key={s.id} className="source-row">
                <span>
                  <span className={s.complete ? 'status-dot on' : 'status-dot bad'} />
                  <b>{s.name}</b> {s.complete ? copy.admin.complete : copy.admin.partial}
                  {s.errors > 0 && <span className="muted"> · {copy.admin.errors(s.errors)}</span>}
                </span>
                <span className="note">{copy.admin.sourceCounts(s.inScope ?? 0, s.new ?? 0, s.closed ?? 0)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
