import { useState, type FormEvent } from 'react'
import { copy } from '../copy'
import { supabase } from '../lib/supabase'

// 가입은 막아 두고(관리자가 Supabase에서 초대한 사람만) 구글 계정으로 들어온다.
// 구글 계정 이메일이 초대한 이메일과 같아야 한다. 이메일 링크는 구글을 못 쓸 때의 예비.

/** 로그인에서 돌아온 주소에 오류가 있으면 읽고 주소에서 지운다. */
function takeRedirectError(): string | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, '') || window.location.search.replace(/^\?/, ''))
  const code = params.get('error_code') ?? params.get('error')
  if (!code) return null
  window.history.replaceState(null, '', window.location.pathname)
  return code === 'signup_disabled' || code === 'access_denied' ? copy.login.notInvited : copy.login.failed
}

export function Login() {
  const [redirectError] = useState(takeRedirectError)
  const [showEmail, setShowEmail] = useState(false)
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle')

  async function google() {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/`, queryParams: { prompt: 'select_account' } },
    })
  }

  async function send(e: FormEvent) {
    e.preventDefault()
    if (!supabase) return
    setState('sending')
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { shouldCreateUser: false, emailRedirectTo: `${window.location.origin}/` },
    })
    setState(error ? 'failed' : 'sent')
  }

  return (
    <div className="login">
      <h1>{copy.appName}</h1>
      <button type="button" className="btn google" onClick={google}>
        <svg viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.2C12.5 13.6 17.8 9.5 24 9.5z" />
          <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.7c4.3-4 6.9-9.9 6.9-17.1z" />
          <path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.2C1 16.5 0 20.1 0 24s1 7.5 2.7 10.8l7.9-6.2z" />
          <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.3-8.5 2.3-6.2 0-11.5-4.1-13.4-9.8l-7.9 6.2C6.6 42.6 14.6 48 24 48z" />
        </svg>
        {copy.login.google}
      </button>
      {redirectError && <p className="note urgent">{redirectError}</p>}

      {!showEmail ? (
        <button type="button" className="text-btn" onClick={() => setShowEmail(true)}>{copy.login.useEmail}</button>
      ) : (
        <form onSubmit={send}>
          <label htmlFor="email">{copy.login.email}</label>
          <input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button type="submit" className="btn" disabled={state === 'sending'}>{copy.login.send}</button>
          {state === 'sent' && <p className="note">{copy.login.sent}</p>}
          {state === 'failed' && <p className="note urgent">{copy.login.failed}</p>}
        </form>
      )}
    </div>
  )
}
