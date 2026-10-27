import { useEffect, useState } from 'react'
import { copy } from '../copy'
import { SectionTitle } from '../components/ui'
import { dateText } from '../lib/format'
import { goBack, href } from '../lib/route'
import { loadNotify, loadTelegramLink, saveNotify, type Loaded, type NotifyPrefs, type TelegramLink } from '../lib/settings'
import { supabase } from '../lib/supabase'
import type { NotifyDefaults, Screen } from '../lib/types'

// 관리 탭: 메뉴(프로필·이력서, 아침 알림, 수집 현황)와 로그인 계정. 메뉴를 누르면 각 화면으로 넘어간다
export function Admin() {
  const [email, setEmail] = useState<string | null>(null)
  useEffect(() => {
    supabase?.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null))
  }, [])

  return (
    <div className="page">
      <header className="page-head"><h1>{copy.tabs.admin}</h1></header>
      <nav className="menu">
        <a className="menu-row" href={href.profile}>{copy.admin.profile}<span aria-hidden="true">›</span></a>
        <a className="menu-row" href={href.notify}>{copy.admin.notify}<span aria-hidden="true">›</span></a>
        <a className="menu-row" href={href.collection}>{copy.admin.collection}<span aria-hidden="true">›</span></a>
      </nav>
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

/** 관리 안 화면의 머리: 뒤로(관리), 제목, 한 줄 설명 */
function SubHead({ title, sub }: { title: string; sub?: string }) {
  return (
    <>
      <div className="topbar">
        <button type="button" className="icon-btn" aria-label={copy.job.back} onClick={() => goBack(href.admin)}>‹</button>
      </div>
      <header className="page-head">
        <h1>{title}</h1>
        {sub && <div className="page-sub">{sub}</div>}
      </header>
    </>
  )
}

/** 아침 알림: 연결 상태와 사람별 설정(settings.notify: 받기, 개수). 고르면 바로 저장한다 */
export function NotifyPage({ defaults }: { defaults?: NotifyDefaults }) {
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

  // Supabase가 없으면(개발) 저장할 곳이 없다
  const editable = !!supabase && !!defaults && typeof prefs === 'object'
  const cur = typeof prefs === 'object' ? prefs : {}
  const enabled = cur.enabled !== false
  const choices = defaults?.choices?.top ?? []
  const top = cur.top && choices.includes(cur.top) ? cur.top : defaults?.top

  function change(next: NotifyPrefs) {
    if (!editable) return
    const before = prefs
    const merged = { ...cur, ...next }
    setPrefs(merged)
    setSaved(null)
    // 실패하면 고르기 전 값으로 되돌린다
    saveNotify(merged).then((ok) => {
      setSaved(ok ? 'ok' : 'failed')
      if (!ok) setPrefs(before)
    })
  }

  let status = null
  if (link === 'missing') status = <p className="note">{copy.admin.linkMissing}</p>
  else if (link === 'failed') status = <p className="note">{copy.admin.loadFailed}</p>
  else if (link) status = <p className="note"><span className="status-dot on" />{copy.admin.linked(link.lastSentOn ? dateText(link.lastSentOn) : null)}</p>
  else if (link === null) status = <p className="note"><span className="status-dot" />{copy.admin.notLinked}</p>

  return (
    <div className="page detail">
      <SubHead title={copy.admin.notify} sub={copy.admin.when} />
      <section className="section">
        <div className="admin-block">
          {status}
          {!defaults && <p className="note">{copy.admin.notifyMissing}</p>}
          {prefs === 'missing' && <p className="note">{copy.admin.prefsMissing}</p>}
          {prefs === 'failed' && <p className="note">{copy.admin.loadFailed}</p>}
          <label className="switch">
            {copy.admin.enabled}
            <input type="checkbox" checked={enabled} disabled={!editable} onChange={(e) => change({ enabled: e.target.checked })} />
          </label>
          {defaults && choices.length > 0 && (
            <label className="field">
              <span>{copy.admin.top}</span>
              <select value={top} disabled={!editable || !enabled} onChange={(e) => change({ top: Number(e.target.value) })}>
                {choices.map((n) => (
                  <option key={n} value={n}>{copy.admin.topOption(n)}{n === defaults.top ? copy.admin.defaultMark : ''}</option>
                ))}
              </select>
            </label>
          )}
          {defaults?.soonMinScore !== undefined && <p className="note small">{copy.admin.prefsNote(defaults.soonMinScore)}</p>}
          {saved && <p className={saved === 'ok' ? 'note' : 'note urgent'} role="status">{saved === 'ok' ? copy.admin.saved : copy.admin.saveFailed}</p>}
        </div>
      </section>
    </div>
  )
}

/** 수집 현황: 오늘 공고를 믿어도 되는지(마지막 수집 시각, 수집처마다 끝까지 받았는지)와 내려감 기준 */
export function CollectionPage({ screen, today }: { screen: Screen; today: string }) {
  const run = screen.collection ?? null
  const sources = run?.sources ?? []
  const partial = sources.filter((s) => !s.complete).map((s) => s.name)
  return (
    <div className="page detail">
      <SubHead title={copy.admin.collection} sub={copy.admin.collectionWhen} />
      <section className="section">
        {!run ? (
          <p className="note">{copy.admin.noCollection}</p>
        ) : (
          <div className="admin-block">
            <p className="run-status">
              <span className={partial.length || run.date < today ? 'status-dot bad' : 'status-dot on'} />
              <b>{copy.admin.lastRun(dateText(run.date), run.finished?.slice(11, 16) ?? '')}</b>
            </p>
            {run.date < today && <p className="note urgent">{copy.admin.notToday}</p>}
            <p className={partial.length ? 'note urgent' : 'note'}>
              {partial.length ? copy.admin.somePartial(partial.join(', ')) : copy.admin.allComplete}
            </p>
            <div className="source-rows">
              {sources.map((s) => (
                <div key={s.id} className="source-row">
                  <span>{s.name}</span>
                  <span className={s.complete ? 'note' : 'note urgent'}>{s.complete ? copy.admin.complete : copy.admin.partial}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <p className="note small rule">{copy.admin.closedRule}</p>
      </section>
    </div>
  )
}
