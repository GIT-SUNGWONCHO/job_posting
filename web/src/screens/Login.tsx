import { useState, type FormEvent } from 'react'
import { copy } from '../copy'
import { supabase } from '../lib/supabase'

// 가입은 막아 두고(관리자가 초대한 사람만), 이메일로 받은 링크를 눌러 들어온다.
export function Login() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle')

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
      <form onSubmit={send}>
        <label htmlFor="email">{copy.login.email}</label>
        <input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <button type="submit" className="btn primary" disabled={state === 'sending'}>{copy.login.send}</button>
      </form>
      {state === 'sent' && <p className="note">{copy.login.sent}</p>}
      {state === 'failed' && <p className="note urgent">{copy.login.failed}</p>}
    </div>
  )
}
