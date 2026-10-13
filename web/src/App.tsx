import { useEffect, useMemo, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { copy } from './copy'
import { SideNav, TabBar } from './components/Nav'
import { passes } from './lib/filter'
import { todayISO } from './lib/format'
import { loadScreen } from './lib/load'
import { useRoute } from './lib/route'
import { loadMatches, type Match } from './lib/matches'
import { loadFilters, saveFilters as saveRemoteFilters } from './lib/settings'
import { readLocal, writeLocal } from './lib/storage'
import { supabase } from './lib/supabase'
import type { Filters, Screen } from './lib/types'
import { useMedia, WIDE } from './lib/useMedia'
import { Admin } from './screens/Admin'
import { CompanyPage } from './screens/CompanyPage'
import { JobDetail } from './screens/JobDetail'
import { Jobs, PAGE, type JobsUi } from './screens/Jobs'
import { Later } from './screens/Later'
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
  const [ui, setUi] = useState<JobsUi>({ query: '', sort: 'latest', limit: PAGE })
  const [matches, setMatches] = useState<Map<string, Match>>(new Map())
  useEffect(() => {
    let alive = true
    loadMatches().then((m) => {
      if (!alive) return
      setMatches(m)
      if (m.size > 0) setUi((u) => (u.sort === 'latest' ? { ...u, sort: 'recommend' } : u))
    })
    return () => {
      alive = false
    }
  }, [])

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
      const p = screen.postings.find((x) => x.id === route.id)
      detail = !wide
      body = wide
        ? <div className="split">{jobs('jobs', route.id)}<JobDetail screen={screen} posting={p} today={today} match={p && matches.get(p.id)} panel /></div>
        : <JobDetail screen={screen} posting={p} today={today} match={p && matches.get(p.id)} />
      break
    }
    case 'company':
      detail = !wide
      body = wide
        ? <div className="split">{jobs('companies')}<CompanyPage screen={screen} companyKey={route.key} today={today} panel /></div>
        : <CompanyPage screen={screen} companyKey={route.key} today={today} />
      break
    case 'career':
      body = <Later title={copy.tabs.career} text={copy.later.career} />
      break
    case 'apply':
      body = <Later title={copy.tabs.apply} text={copy.later.apply} />
      break
    case 'admin':
      body = <Admin />
      break
    case 'profile':
      detail = !wide
      body = <Profile jobTypes={screen.jobTypes ?? []} />
      break
  }

  return (
    <div className={wide ? 'shell wide' : detail ? 'shell detail-only' : 'shell'}>
      {wide && <SideNav route={route} />}
      <main className="content">{body}</main>
      {!wide && !detail && <TabBar route={route} />}
    </div>
  )
}
