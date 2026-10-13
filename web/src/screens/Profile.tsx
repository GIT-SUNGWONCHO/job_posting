import { useEffect, useState, type KeyboardEvent } from 'react'
import { copy } from '../copy'
import { SectionTitle } from '../components/ui'
import { careerYears, emptyProfile, loadProfile, saveProfile, type Job, type Profile as P, type Project } from '../lib/profile'
import { goBack, href } from '../lib/route'
import type { JobType } from '../lib/types'

const t = copy.profile

function replaceAt<T>(list: T[], i: number, v: T): T[] {
  return list.map((x, j) => (j === i ? v : x))
}

export function Profile({ jobTypes, panel = false }: { jobTypes: JobType[]; panel?: boolean }) {
  const [profile, setProfile] = useState<P>(emptyProfile)
  const [version, setVersion] = useState(0)
  const [skill, setSkill] = useState('')
  const [state, setState] = useState<'loading' | 'idle' | 'saving' | 'saved' | 'failed'>('loading')

  useEffect(() => {
    let alive = true
    loadProfile().then((r) => {
      if (!alive) return
      if (r) {
        setProfile(r.profile)
        setVersion(r.version)
      }
      setState('idle')
    })
    return () => {
      alive = false
    }
  }, [])

  const edit = (p: P) => {
    setProfile(p)
    if (state === 'saved' || state === 'failed') setState('idle')
  }
  const years = careerYears(profile.careerStart)

  async function save() {
    setState('saving')
    const next = version + 1
    const ok = await saveProfile(profile, next)
    if (ok) setVersion(next)
    setState(ok ? 'saved' : 'failed')
  }

  function addSkill() {
    const v = skill.trim()
    if (v && !profile.skills.includes(v)) edit({ ...profile, skills: [...profile.skills, v] })
    setSkill('')
  }
  function onSkillKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault()
      addSkill()
    }
  }

  const setJob = (i: number, j: Job) => edit({ ...profile, jobs: replaceAt(profile.jobs, i, j) })
  const setProject = (i: number, p: Project) => edit({ ...profile, projects: replaceAt(profile.projects, i, p) })

  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && (
        <div className="topbar">
          <button type="button" className="icon-btn" aria-label={copy.job.back} onClick={() => goBack(href.admin)}>‹</button>
        </div>
      )}
      <header className="page-head">
        <h1>{t.title}</h1>
        {(years !== null || version > 0) && (
          <div className="page-sub">{[years !== null && t.years(years), version > 0 && `v${version}`].filter(Boolean).join(' · ')}</div>
        )}
      </header>

      <section className="section form">
        <SectionTitle>{t.basics}</SectionTitle>
        <label className="field">
          <span>{t.careerStart}</span>
          <input type="month" value={profile.careerStart} onChange={(e) => edit({ ...profile, careerStart: e.target.value })} />
        </label>
        <label className="field">
          <span>{t.currentRole}</span>
          <select value={profile.currentRole} onChange={(e) => edit({ ...profile, currentRole: e.target.value })}>
            <option value="">{t.choose}</option>
            {jobTypes.map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
          </select>
        </label>
        <div className="field">
          <span>{t.targetRoles}</span>
          <div className="chips wrap">
            {jobTypes.map((j) => {
              const on = profile.targetRoles.includes(j.id)
              return (
                <button key={j.id} type="button" className={on ? 'chip selected' : 'chip'} aria-pressed={on}
                  onClick={() => edit({ ...profile, targetRoles: on ? profile.targetRoles.filter((x) => x !== j.id) : [...profile.targetRoles, j.id] })}>
                  {j.name}
                </button>
              )
            })}
          </div>
        </div>
      </section>

      <section className="section form">
        <SectionTitle right={<button type="button" className="text-link" onClick={() => edit({ ...profile, jobs: [...profile.jobs, { company: '', industry: '', start: '', end: '', role: '' }] })}>{t.add}</button>}>
          {t.jobs}
        </SectionTitle>
        {profile.jobs.map((j, i) => (
          <div key={i} className="entry">
            <div className="row2">
              <label className="field"><span>{t.company}</span>
                <input value={j.company} onChange={(e) => setJob(i, { ...j, company: e.target.value })} />
              </label>
              <label className="field"><span title={t.industryHelp}>{t.industry} <span className="help" aria-label={t.industryHelp}>?</span></span>
                <input value={j.industry} placeholder={t.industryPlaceholder} onChange={(e) => setJob(i, { ...j, industry: e.target.value })} />
              </label>
            </div>
            <div className="row2">
              <label className="field"><span>{t.start}</span>
                <input type="month" value={j.start} onChange={(e) => setJob(i, { ...j, start: e.target.value })} />
              </label>
              <label className="field"><span>{t.end}</span>
                <input type="month" value={j.end} placeholder={t.endPlaceholder} onChange={(e) => setJob(i, { ...j, end: e.target.value })} />
              </label>
            </div>
            <label className="field"><span>{t.role}</span>
              <input value={j.role} placeholder={t.rolePlaceholder} onChange={(e) => setJob(i, { ...j, role: e.target.value })} />
            </label>
            <button type="button" className="text-link danger" onClick={() => edit({ ...profile, jobs: profile.jobs.filter((_, k) => k !== i) })}>{t.remove}</button>
          </div>
        ))}
      </section>

      <section className="section form">
        <SectionTitle right={<button type="button" className="text-link" onClick={() => edit({ ...profile, projects: [...profile.projects, { title: '', result: '' }] })}>{t.add}</button>}>
          {t.projects}{profile.projects.length > 0 && <span className="count"> {profile.projects.length}</span>}
        </SectionTitle>
        {profile.projects.map((p, i) => (
          <div key={i} className="entry">
            <label className="field"><span>{t.projectTitle}</span>
              <input value={p.title} onChange={(e) => setProject(i, { ...p, title: e.target.value })} />
            </label>
            <label className="field"><span>{t.result}</span>
              <textarea rows={2} value={p.result} placeholder={t.resultPlaceholder} onChange={(e) => setProject(i, { ...p, result: e.target.value })} />
            </label>
            <button type="button" className="text-link danger" onClick={() => edit({ ...profile, projects: profile.projects.filter((_, k) => k !== i) })}>{t.remove}</button>
          </div>
        ))}
      </section>

      <section className="section form">
        <SectionTitle>{t.skills}</SectionTitle>
        {profile.skills.length > 0 && (
          <div className="chips wrap">
            {profile.skills.map((s) => (
              <button key={s} type="button" className="chip" aria-label={`${s} ${t.remove}`}
                onClick={() => edit({ ...profile, skills: profile.skills.filter((x) => x !== s) })}>
                {s} ×
              </button>
            ))}
          </div>
        )}
        <div className="inline-add">
          <input value={skill} placeholder={t.skillPlaceholder} onChange={(e) => setSkill(e.target.value)} onKeyDown={onSkillKey} />
          <button type="button" className="btn" onClick={addSkill}>{t.add}</button>
        </div>
      </section>

      <div className="savebar">
        {state === 'saved' && <span className="note">{t.saved}</span>}
        {state === 'failed' && <span className="note urgent">{t.failed}</span>}
        <button type="button" className="btn primary" disabled={state === 'loading' || state === 'saving'} onClick={save}>{t.save}</button>
      </div>
    </div>
  )
}
