import { copy } from '../copy'
import { href, type Route } from '../lib/route'

const TABS = [
  { key: 'report', href: href.report, label: copy.tabs.report, icon: 'M4 5h16v3H4zM4 11h10v3H4zM4 17h13v3H4z' },
  { key: 'jobs', href: href.jobs, label: copy.tabs.jobs, icon: 'M4 6h16v13H4zM9 3h6v3H9z' },
  { key: 'career', href: href.career, label: copy.tabs.career, icon: 'M4 19l5-6 4 3 7-9v12H4z' },
  { key: 'apply', href: href.apply, label: copy.tabs.apply, icon: 'M5 4h14v16l-7-4-7 4z' },
  { key: 'admin', href: href.admin, label: copy.tabs.admin, icon: 'M12 8a4 4 0 100 8 4 4 0 000-8zM11 2h2v4h-2zM11 18h2v4h-2zM2 11h4v2H2zM18 11h4v2h-4z' },
] as const

function activeTab(route: Route): string {
  if (route.name === 'job' || route.name === 'company') return 'jobs'
  if (route.name === 'profile' || route.name === 'notify' || route.name === 'collection') return 'admin'
  return route.name
}

export function TabBar({ route }: { route: Route }) {
  const active = activeTab(route)
  return (
    <nav className="tabbar" aria-label="메뉴">
      {TABS.map((t) => (
        <a key={t.key} href={t.href} className={t.key === active ? 'tab active' : 'tab'} aria-current={t.key === active ? 'page' : undefined}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={t.icon} /></svg>
          {t.label}
        </a>
      ))}
    </nav>
  )
}

export function SideNav({ route }: { route: Route }) {
  const active = activeTab(route)
  return (
    <nav className="sidenav" aria-label="메뉴">
      <div className="sidenav-name">{copy.appName}</div>
      {TABS.map((t) => (
        <a key={t.key} href={t.href} className={t.key === active ? 'side active' : 'side'} aria-current={t.key === active ? 'page' : undefined}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={t.icon} /></svg>
          {t.label}
        </a>
      ))}
    </nav>
  )
}
