import { copy } from '../copy'
import { href, type Route } from '../lib/route'

// 선 아이콘(24, 굵기 1.8은 app.css). 지금 탭만 블루
const TABS = [
  { key: 'report', href: href.report, label: copy.tabs.report, icon: 'M4 10.2 12 4l8 6.2V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z' },
  { key: 'jobs', href: href.jobs, label: copy.tabs.jobs, icon: 'M7.5 3.5h9A2.5 2.5 0 0 1 19 6v12a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 18V6a2.5 2.5 0 0 1 2.5-2.5zM9 9h6M9 13h6M9 17h3.5' },
  { key: 'career', href: href.career, label: copy.tabs.career, icon: 'M4 17.5 9.5 12l3.5 3.5L20 8.5M15 8.5h5v5' },
  { key: 'apply', href: href.apply, label: copy.tabs.apply, icon: 'M6.5 4h11v16L12 16.5 6.5 20z' },
  { key: 'admin', href: href.admin, label: copy.tabs.admin, icon: 'M4 7.5h9M17 7.5h3M4 16.5h3M11 16.5h9M17 7.5a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM11 16.5a2 2 0 1 1-4 0 2 2 0 0 1 4 0z' },
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
