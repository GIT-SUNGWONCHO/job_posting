import { useEffect, useMemo, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { copy } from './copy'
import { SideNav, TabBar } from './components/Nav'
import { passes } from './lib/filter'
import { todayISO } from './lib/format'
import { loadScreen } from './lib/load'
import { useRoute } from './lib/route'
import { AppsContext, loadApplications, type Application } from './lib/applications'
import { loadFeedback, type Feedback } from './lib/feedback'
import { loadMatches, type Match } from './lib/matches'
import { StarsContext, loadStars, saveStar, type StarsState } from './lib/stars'
import { loadFilters, saveFilters as saveRemoteFilters } from './lib/settings'
import { readLocal, writeLocal } from './lib/storage'
import { supabase } from './lib/supabase'
import type { Filters, Screen } from './lib/types'
import { useMedia, WIDE } from './lib/useMedia'
import { Admin, CollectionPage, NotifyPage } from './screens/Admin'
import { Apply } from './screens/Apply'
import { Career } from './screens/Career'
import { CompanyPage } from './screens/CompanyPage'
import { JobDetail } from './screens/JobDetail'
import { Jobs, PAGE, type JobsUi } from './screens/Jobs'
import { Login } from './screens/Login'
import { Profile } from './screens/Profile'
import { Report } from './screens/Report'

const FILTER_KEY = 'jobpost.filters.v1'

function useSession(): Session | null | undefined {
  // undefined: 확인 중, null: 로그인 안 함. Supabase가 없으면(개발) 로그인 없이 쓴다
  const [session, setSession] = useState<Session | null | undefined>(supabase ? undefined : null)
  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])
  return session
}

export default function App() {
  const session = useSession()
  const needLogin = supabase !== null && session === null
  const ready = supabase === null || !!session

  const [screen, setScreen] = useState<Screen | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!ready) return
    let alive = true
    loadScreen().then(
      (s) => alive && setScreen(s),
      () => alive && setError(true),
    )
    return () => {
      alive = false
    }
  }, [ready, attempt])

  if (needLogin) return <Login />
  if (error) {
    return (
      <div className="center">
        <p>{copy.load.failed}</p>
        <button type="button" className="btn" onClick={() => { setError(false); setAttempt((a) => a + 1) }}>{copy.load.retry}</button>
      </div>
    )
  }
  if (!screen) return <div className="center muted">{copy.load.loading}</div>
  return <Main screen={screen} />
}

function Main({ screen }: { screen: Screen }) {
  const route = useRoute()
  const wide = useMedia(WIDE)
  const today = todayISO()
  const defaults = screen.defaultFilters
  // 예전에 저장한 필터에 없는 항목(새로 생긴 직무 유형 등)은 기본값으로 채운다
  const [filters, setFilters] = useState<Filters>(() => ({ ...defaults, ...(readLocal<Filters>(FILTER_KEY) ?? {}) }))
  const [ui, setUi] = useState<JobsUi>({ query: '', sort: 'latest', limit: PAGE, sample: false, starred: false })
  const [scored, setScored] = useState<Map<string, Match>>(new Map())
  const [feedback, setFeedback] = useState<Map<string, Feedback>>(new Map())
  const [apps, setApps] = useState<Map<string, Application>>(new Map())
  const [stars, setStars] = useState<StarsState>(undefined)
  useEffect(() => {
    let alive = true
    loadMatches().then((m) => {
      if (!alive) return
      setScored(m)
      if (m.size > 0) setUi((u) => (u.sort === 'latest' ? { ...u, sort: 'recommend' } : u))
    })
    loadFeedback().then((f) => alive && setFeedback(f))
    loadApplications().then((a) => alive && setApps(a))
    loadStars().then((s) => alive && setStars(s))
    return () => {
      alive = false
    }
  }, [])
  // 목록에 내 평가(○△×)를 함께 보여준다
  const matches = useMemo(() => {
    const out = new Map<string, Match>()
    for (const [id, m] of scored) out.set(id, feedback.has(id) ? { ...m, mine: feedback.get(id)!.label } : m)
    return out
  }, [scored, feedback])
  const onFeedback = (id: string, f: Feedback) => setFeedback((prev) => new Map(prev).set(id, f))
  // 저장 중인 회사의 ★는 다시 눌러도 무시한다(켜기·끄기 요청이 엇갈려 화면과 저장이 어긋나지 않게)
  const starSaving = useRef(new Set<string>())
  const starsValue = useMemo(() => ({
    state: stars,
    toggle: (key: string) => {
      if (!(stars instanceof Set) || starSaving.current.has(key)) return
      const on = !stars.has(key)
      const put = (value: boolean) => setStars((prev) => {
        if (!(prev instanceof Set)) return prev
        const next = new Set(prev)
        if (value) next.add(key)
        else next.delete(key)
        return next
      })
      starSaving.current.add(key)
      put(on)
      // 실패하면 누르기 전 값으로 되돌린다(그사이 바뀐 상태를 한 번 더 뒤집지 않는다)
      saveStar(key, on).then((ok) => { if (!ok) put(!on) }).finally(() => starSaving.current.delete(key))
    },
  }), [stars])
  const onApp = (id: string, a: Application | null) => setApps((prev) => {
    const next = new Map(prev)
    if (a) next.set(id, a)
    else next.delete(id)
    return next
  })

  const passed = useMemo(
    () => screen.postings.filter((p) => !p.noise && passes(p, screen.companies[p.company], filters)),
    [screen, filters],
  )
  const regions = useMemo(() => {
    const n = new Map<string, number>()
    for (const p of screen.postings) for (const r of p.regions) n.set(r, (n.get(r) ?? 0) + 1)
    const top = [...n.entries()].filter(([r]) => r !== '원격').sort((a, b) => b[1] - a[1]).map(([r]) => r).slice(0, 16)
    return [...top, '원격']
  }, [screen])

  // 계정에 저장된 필터가 있으면 그걸 쓰고, 없으면 이 기기에 있던 필터를 계정으로 옮긴다
  useEffect(() => {
    let alive = true
    loadFilters().then((remote) => {
      if (!alive) return
      if (remote) {
        const merged = { ...defaults, ...remote }
        setFilters(merged)
        writeLocal(FILTER_KEY, merged)
      } else {
        saveRemoteFilters({ ...defaults, ...(readLocal<Filters>(FILTER_KEY) ?? {}) })
      }
    })
    return () => {
      alive = false
    }
  }, [defaults])

  function saveFilters(f: Filters) {
    setFilters(f)
    writeLocal(FILTER_KEY, f)
    saveRemoteFilters(f)
    setUi({ ...ui, limit: PAGE })
  }

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [route.name])

  const jobs = (seg: 'jobs' | 'companies', activeId?: string) => (
    <Jobs screen={screen} passed={passed} filters={filters} defaults={defaults} regions={regions} seg={seg}
      ui={ui} setUi={setUi} onFilters={saveFilters} today={today} activeId={activeId} matches={matches} />
  )

  let body
  let detail = false
  switch (route.name) {
    case 'report':
      body = <Report screen={screen} passed={passed} today={today} matches={matches} />
      break
    case 'jobs':
      body = jobs(route.seg)
      break
    case 'job': {
      // 최근 7일 안에 내려간 공고도 연다(수집 현황의 내려간 공고)
      const p = screen.postings.find((x) => x.id === route.id) ?? screen.closed?.find((x) => x.id === route.id)
      detail = !wide
      body = wide
        ? <div className="split">{jobs('jobs', route.id)}<JobDetail screen={screen} posting={p} today={today} match={p && matches.get(p.id)}
          feedback={p && feedback.get(p.id)} onFeedback={onFeedback} app={p && apps.get(p.id)} onApp={onApp} panel /></div>
        : <JobDetail screen={screen} posting={p} today={today} match={p && matches.get(p.id)}
          feedback={p && feedback.get(p.id)} onFeedback={onFeedback} app={p && apps.get(p.id)} onApp={onApp} />
      break
    }
    case 'company':
      detail = !wide
      body = wide
        ? <div className="split">{jobs('companies')}<CompanyPage key={route.key} screen={screen} companyKey={route.key} today={today} filters={filters} panel /></div>
        : <CompanyPage key={route.key} screen={screen} companyKey={route.key} today={today} filters={filters} />
      break
    case 'career':
      body = <Career screen={screen} seg={route.seg} filters={filters} matches={matches} today={today} />
      break
    case 'apply':
      body = <Apply screen={screen} apps={apps} today={today} onApp={onApp} />
      break
    case 'admin':
      body = <Admin />
      break
    case 'notify':
      detail = !wide
      body = <NotifyPage defaults={screen.notify} />
      break
    case 'collection':
      detail = !wide
      body = <CollectionPage screen={screen} today={today} filters={filters} matches={matches} />
      break
    case 'profile':
      detail = !wide
      body = <Profile options={screen.profileOptions} skillOptions={screen.skills ?? []} />
      break
  }

  return (
    <AppsContext.Provider value={apps}>
      <StarsContext.Provider value={starsValue}>
      <div className={wide ? 'shell wide' : detail ? 'shell detail-only' : 'shell'}>
        {wide && <SideNav route={route} />}
        <main className="content">{body}</main>
        {!wide && !detail && <TabBar route={route} />}
      </div>
      </StarsContext.Provider>
    </AppsContext.Provider>
  )
}
