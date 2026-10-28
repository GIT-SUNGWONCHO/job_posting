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

/** 아침 알림: 연결 상태, 받기 켜기·끄기(settings.notify.enabled), 알림에 들어가는 것 */
export function NotifyPage({ defaults }: { defaults?: NotifyDefaults }) {
  const [prefs, setPrefs] = useState<Loaded<NotifyPrefs> | undefined>(undefined)
  const [link, setLink] = useState<Loaded<TelegramLink | null> | undefined>(undefined)
  const [saved, setSaved] = useState<'ok' | 'failed' | null>(null)
  // 저장하는 동안은 다시 누르지 못하게(켜기·끄기 요청이 엇갈려 화면과 저장이 어긋나지 않게)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    let alive = true
    loadNotify().then((p) => alive && setPrefs(p))
    loadTelegramLink().then((l) => alive && setLink(l))
    return () => {
      alive = false
    }
  }, [])

  // Supabase가 없으면(개발) 저장할 곳이 없다
  const editable = !!supabase && typeof prefs === 'object'
  const enabled = !(typeof prefs === 'object' && prefs.enabled === false)

  function toggle(on: boolean) {
    if (!editable || saving) return
    const before = prefs
    const next = { ...prefs, enabled: on }
    setPrefs(next)
    setSaved(null)
    setSaving(true)
    // 실패하면 누르기 전 값으로 되돌린다
    saveNotify(next).then((ok) => {
      setSaved(ok ? 'ok' : 'failed')
      if (!ok) setPrefs(before)
    }).finally(() => setSaving(false))
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
          {prefs === 'missing' && <p className="note">{copy.admin.prefsMissing}</p>}
          {prefs === 'failed' && <p className="note">{copy.admin.loadFailed}</p>}
          <label className="switch">
            {copy.admin.enabled}
            <input type="checkbox" checked={enabled} disabled={!editable || saving} onChange={(e) => toggle(e.target.checked)} />
          </label>
          {saved && <p className={saved === 'ok' ? 'note' : 'note urgent'} role="status">{saved === 'ok' ? copy.admin.saved : copy.admin.saveFailed}</p>}
        </div>
      </section>
      <section className="section">
        <SectionTitle>{copy.admin.contents}</SectionTitle>
        <ul className="plain-list">
          {copy.admin.contentLines(defaults?.soonMinScore, defaults?.soonDays).map((line) => <li key={line}>{line}</li>)}
        </ul>
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
        {!run || sources.length === 0 ? (
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
