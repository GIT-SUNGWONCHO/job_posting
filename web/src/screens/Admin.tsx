import { useEffect, useState } from 'react'
import { copy } from '../copy'
import { SectionTitle } from '../components/ui'
import { href } from '../lib/route'
import { supabase } from '../lib/supabase'

// 관리 탭. 3단계에서 프로필·필터가 들어오기 전까지는 로그인 계정만 보여준다.
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
