import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { BACK_ICON, RIGHT_ICON, SEARCH_ICON, SectionTitle, Sep } from '../components/ui'
import { dateText } from '../lib/format'
import { durationText, loadProfile, months, type Profile } from '../lib/profile'
import { goBack, href, type ListKind } from '../lib/route'
import { loadNotify, loadTelegramLink, saveNotify, type Loaded, type NotifyPrefs, type TelegramLink } from '../lib/settings'
import { supabase } from '../lib/supabase'
import type { NotifyDefaults, Screen } from '../lib/types'

const t = copy.admin

function MenuRow({ to, label, status }: { to: string; label: string; status?: ReactNode }) {
  return (
    <a className="menu-row" href={to}>
      <span className="menu-label">{label}</span>
      {status && <span className="menu-status">{status}</span>}
      {RIGHT_ICON}
    </a>
  )
}

/** 상태 점: 연결됨 · 정상은 초록, 문제는 빨강, 꺼짐은 회색 */
const Dot = ({ kind }: { kind: 'ok' | 'bad' | 'off' }) => <span className={`status-dot ${kind}`} aria-hidden="true" />

// 관리 탭: 메뉴(오른쪽에 지금 상태) · 목록(스킬 · 직무 유형 · 업종) · 계정 · 개발용(점선 칸)
export function Admin({ screen, showRatings, onShowRatings, onSample }: {
  screen: Screen
  showRatings: boolean
  onShowRatings: (on: boolean) => void
  onSample: () => void
}) {
  const [email, setEmail] = useState<string | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [prefs, setPrefs] = useState<Loaded<NotifyPrefs> | undefined>(undefined)
  const [link, setLink] = useState<Loaded<TelegramLink | null> | undefined>(undefined)
  useEffect(() => {
    let alive = true
    supabase?.auth.getUser().then(({ data }) => alive && setEmail(data.user?.email ?? null))
    loadProfile().then((r) => alive && setProfile(r?.profile ?? null))
    loadNotify().then((p) => alive && setPrefs(p))
    loadTelegramLink().then((l) => alive && setLink(l))
    return () => {
      alive = false
    }
  }, [])
  const total = profile ? profile.careers.reduce((s, c) => s + months(c.start, c.end), 0) : 0
  const off = typeof prefs === 'object' && prefs.enabled === false
  const linked = link && typeof link === 'object'
  const run = screen.collection
  const partial = run?.sources.some((s) => !s.complete)
  const sample = screen.sample ?? []
  return (
    <div className="page admin">
      <div className="list-top"><h1>{copy.tabs.admin}</h1></div>
      <nav className="menu">
        <MenuRow to={href.profile} label={t.profile} status={total > 0 ? t.careerTotal(durationText(total)) : undefined} />
        <MenuRow to={href.notify} label={t.notify} status={off ? t.off : linked ? t.onTelegram : link === null ? t.notLinkedShort : undefined} />
        <MenuRow to={href.collection} label={t.collection}
          status={run ? `${dateText(run.date)} ${run.finished?.slice(11, 16) ?? ''} · ${partial ? t.partial : t.complete}` : undefined} />
      </nav>
      <div className="band" />
      <div className="group-label">{t.lists}</div>
      <nav className="menu">
        <MenuRow to={href.list('skills')} label={t.skills} status={(screen.skills ?? []).length.toLocaleString()} />
        <MenuRow to={href.list('jobtypes')} label={t.jobTypes} status={screen.jobTypes.length} />
        <MenuRow to={href.list('industries')} label={t.industries} status={screen.profileOptions?.industries.length} />
      </nav>
      {supabase && (
        <>
          <div className="band" />
          <div className="group-label">{t.account}</div>
          <div className="menu-row account">
            <span className="account-mail">{email ?? ''}</span>
            <button type="button" className="btn small" onClick={() => supabase?.auth.signOut()}>{t.logout}</button>
          </div>
        </>
      )}
      <div className="band" />
      <div className="dev-box">
        <span className="dev-tag">{t.devTag}</span>
        <label className="toggle-row">
          <span>{t.showRatings}</span>
          <input type="checkbox" className="switch-ui" checked={showRatings} onChange={(e) => onShowRatings(e.target.checked)} />
        </label>
        {sample.length > 0 && (
          <button type="button" className="toggle-row link" onClick={onSample}>
            <span>{t.sample}</span><span className="muted-sm">{sample.length}{RIGHT_ICON}</span>
          </button>
        )}
      </div>
    </div>
  )
}

/** 관리 안 화면의 머리: 뒤로(관리), 제목, 그 아래 한 줄(상태) */
function SubHead({ title, count, children }: { title: string; count?: number; children?: ReactNode }) {
  return (
    <>
      <div className="topbar">
        <button type="button" className="icon-btn" aria-label={copy.common.back} onClick={() => goBack(href.admin)}>{BACK_ICON}</button>
      </div>
      <header className="detail-head sub-head-page">
        <h1>{title}{count !== undefined && <span className="h1-count">{count.toLocaleString()}</span>}</h1>
        {children}
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

  let status: ReactNode = null
  if (link === 'missing') status = <span className="muted-sm">{t.linkMissing}</span>
  else if (link === 'failed') status = <span className="muted-sm">{t.loadFailed}</span>
  else if (link) status = <><Dot kind="ok" /><span>{t.linkedShort}</span><Sep /><span className="muted">{t.lastSent(link.lastSentOn ? dateText(link.lastSentOn) : null)}</span></>
  else if (link === null) status = <><Dot kind="off" /><span>{t.notLinked}</span></>

  return (
    <div className="page detail">
      <SubHead title={t.notify}>{status && <div className="status-line">{status}</div>}</SubHead>
      <label className="menu-row toggle-line">
        <span className="menu-label">{t.enabled}</span>
        <input type="checkbox" className="switch-ui" checked={enabled} disabled={!editable || saving} onChange={(e) => toggle(e.target.checked)} />
      </label>
      {(prefs === 'missing' || prefs === 'failed' || saved) && (
        <p className={saved === 'failed' ? 'note urgent pad-note' : 'note pad-note'} role="status">
          {prefs === 'missing' ? t.prefsMissing : prefs === 'failed' ? t.loadFailed : saved === 'ok' ? t.saved : t.saveFailed}
        </p>
      )}
      <section className="section">
        <SectionTitle>{t.contents}</SectionTitle>
        <div className="kv2 wide plain">
          {t.contentRows(defaults?.soonMinScore, defaults?.soonDays).map(([k, v]) => (
            <ContentRow key={k} k={k} v={v} />
          ))}
        </div>
      </section>
    </div>
  )
}

const ContentRow = ({ k, v }: { k: string; v: string }) => <><span className="k">{k}</span><span className="v pre">{v}</span></>

/** 수집 현황: 오늘 공고를 믿어도 되는지(마지막 수집 시각, 수집처마다 끝까지 받았는지). 내려감 기준은 ⓘ */
export function CollectionPage({ screen, today }: { screen: Screen; today: string }) {
  const run = screen.collection ?? null
  const sources = run?.sources ?? []
  const partial = sources.filter((s) => !s.complete).map((s) => s.name)
  const fresh = !!run && run.date >= today
  return (
    <div className="page detail">
      <SubHead title={t.collection}>
        {run && (
          <div className="status-line">
            <Dot kind={fresh && !partial.length ? 'ok' : 'bad'} />
            <b>{fresh ? t.doneToday : t.notToday}</b><Sep /><span className="muted">{dateText(run.date)} {run.finished?.slice(11, 16) ?? ''}</span>
          </div>
        )}
      </SubHead>
      <section className="section">
        <SectionTitle count={sources.length} info={t.closedRule}>{t.sources}</SectionTitle>
        {sources.length === 0 ? <p className="note">{t.noCollection}</p> : (
          <div className="source-rows">
            {sources.map((s) => (
              <div key={s.id} className="source-row">
                <b>{s.name}</b>
                <span className="source-state"><Dot kind={s.complete ? 'ok' : 'bad'} />{s.complete ? t.complete : t.partial}</span>
              </div>
            ))}
          </div>
        )}
        {partial.length > 0 && <p className="note urgent">{t.somePartial(partial.join(', '))}</p>}
      </section>
    </div>
  )
}

const PAGE = 50

/** 관리 › 목록: 스킬(공고에 나온 스킬, 공고 많은 순, 내 스킬은 숙련도와), 직무 유형(열린 공고 수), 업종 */
export function ListPage({ screen, kind }: { screen: Screen; kind: ListKind }) {
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const [profile, setProfile] = useState<Profile | null>(null)
  useEffect(() => {
    if (kind !== 'skills') return
    let alive = true
    loadProfile().then((r) => alive && setProfile(r?.profile ?? null))
    return () => {
      alive = false
    }
  }, [kind])
  const levels = useMemo(() => screen.profileOptions?.skill_levels ?? [], [screen])
  const mine = useMemo(() => new Map((profile?.skills ?? []).map((s) => [s.name, s.level])), [profile])
  const rows: { name: string; right?: string; tag?: string }[] = useMemo(() => {
    if (kind === 'skills') {
      return (screen.skills ?? []).map((s) => {
        const lv = mine.get(s.name)
        const level = lv !== undefined ? levels.find((l) => l.level === lv)?.name : undefined
        return { name: s.name, right: t.postings(s.count), tag: lv !== undefined ? t.mySkill(level ?? '') : undefined }
      })
    }
    if (kind === 'jobtypes') {
      const open = new Map<string, number>()
      for (const p of screen.postings) if (!p.noise && p.jobType) open.set(p.jobType, (open.get(p.jobType) ?? 0) + 1)
      return screen.jobTypes.map((j) => ({ name: j.name, right: t.postings(open.get(j.id) ?? 0) })).sort((a, b) => a.name.localeCompare(b.name, 'ko'))
    }
    return (screen.profileOptions?.industries ?? []).map((i) => ({ name: i.name }))
  }, [kind, screen, mine, levels])
  const query = q.trim().toLowerCase()
  const shown = query ? rows.filter((r) => r.name.toLowerCase().includes(query)) : rows
  const title = { skills: t.skills, jobtypes: t.jobTypes, industries: t.industries }[kind]
  return (
    <div className="page detail">
      <SubHead title={title} count={rows.length} />
      <div className="list-tools">
        <label className="search-box">{SEARCH_ICON}<input type="search" value={q} placeholder={t.find(title)} aria-label={t.find(title)} onChange={(e) => { setQ(e.target.value); setLimit(PAGE) }} /></label>
        {kind === 'skills' && <span className="muted-sm">{t.skillSort}</span>}
      </div>
      <div className="plain-rows">
        {shown.slice(0, limit).map((r) => (
          <div key={r.name} className="plain-row">
            <span className="plain-name"><b>{r.name}</b>{r.tag && <span className="tag">{r.tag}</span>}</span>
            {r.right && <span className="muted-sm">{r.right}</span>}
          </div>
        ))}
      </div>
      {shown.length > limit && (
        <div className="list-more"><button type="button" className="btn block more" onClick={() => setLimit(limit + PAGE)}>{copy.jobs.more(Math.min(PAGE, shown.length - limit))}</button></div>
      )}
    </div>
  )
}
