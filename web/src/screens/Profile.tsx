import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { copy } from '../copy'
import { SectionTitle } from '../components/ui'
import {
  careerTotals, emptyCareer, emptyProfile, emptyProject, emptyRole, loadProfile, roleYears, saveProfile, yearsText,
  type Career, type Profile as P, type Project, type Role,
} from '../lib/profile'
import { goBack, href } from '../lib/route'
import type { ProfileOptions, SkillOption } from '../lib/types'

const t = copy.profile

function replaceAt<T>(list: T[], i: number, v: T): T[] {
  return list.map((x, j) => (j === i ? v : x))
}
const without = <T,>(list: T[], i: number) => list.filter((_, j) => j !== i)

function Period({ start, end, onChange }: { start: string; end: string; onChange: (start: string, end: string) => void }) {
  return (
    <div className="row2">
      <label className="field"><span>{t.start}</span>
        <input type="month" value={start} onChange={(e) => onChange(e.target.value, end)} />
      </label>
      <label className="field"><span>{t.end}</span>
        <input type="month" value={end} placeholder={t.endPlaceholder} onChange={(e) => onChange(start, e.target.value)} />
      </label>
    </div>
  )
}

function Select({ label, value, options, onChange }: {
  label: string; value: string; options: { id: string; name: string }[]; onChange: (v: string) => void
}) {
  return (
    <label className="field"><span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t.choose}</option>
        {options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </label>
  )
}

const asOptions = (xs: string[]) => xs.map((x) => ({ id: x, name: x }))

function ProjectEntry({ p, opts, mySkills, onChange, onRemove }: {
  p: Project; opts: ProfileOptions; mySkills: string[]; onChange: (p: Project) => void; onRemove: () => void
}) {
  return (
    <div className="entry nested">
      <label className="field"><span>{t.projectTitle}</span>
        <input value={p.title} onChange={(e) => onChange({ ...p, title: e.target.value })} />
      </label>
      <Period start={p.start} end={p.end} onChange={(start, end) => onChange({ ...p, start, end })} />
      <Select label={t.part} value={p.part} options={asOptions(opts.project_parts)} onChange={(part) => onChange({ ...p, part })} />
      <label className="field"><span>{t.summary}</span>
        <textarea rows={2} value={p.summary} placeholder={t.summaryPlaceholder} onChange={(e) => onChange({ ...p, summary: e.target.value })} />
      </label>
      <div className="field"><span>{t.projectSkills}</span>
        {p.skills.length > 0 && <div className="chips wrap small">{p.skills.map((s) => <span key={s} className="chip">{s}</span>)}</div>}
        {mySkills.length ? (
          <details className="pick">
            <summary>{t.pickSkills}</summary>
            <div className="chips wrap">
              {mySkills.map((s) => {
                const on = p.skills.includes(s)
                return (
                  <button key={s} type="button" className={on ? 'chip selected' : 'chip'} aria-pressed={on}
                    onClick={() => onChange({ ...p, skills: on ? p.skills.filter((x) => x !== s) : [...p.skills, s] })}>{s}</button>
                )
              })}
            </div>
          </details>
        ) : <span className="note">{t.projectSkillsEmpty}</span>}
      </div>
      <button type="button" className="text-link danger" onClick={onRemove}>{t.removeProject}</button>
    </div>
  )
}

function RoleEntry({ r, opts, mySkills, onChange, onRemove }: {
  r: Role; opts: ProfileOptions; mySkills: string[]; onChange: (r: Role) => void; onRemove: () => void
}) {
  return (
    <div className="entry nested">
      <Select label={t.role} value={r.role} options={opts.roles} onChange={(role) => onChange({ ...r, role })} />
      {r.role === 'other' && (
        <label className="field"><span>{t.roleName}</span>
          <input value={r.roleName ?? ''} onChange={(e) => onChange({ ...r, roleName: e.target.value })} />
        </label>
      )}
      <Period start={r.start} end={r.end} onChange={(start, end) => onChange({ ...r, start, end })} />
      <label className="field"><span>{t.roleSummary}</span>
        <textarea rows={2} value={r.summary} placeholder={t.roleSummaryPlaceholder} onChange={(e) => onChange({ ...r, summary: e.target.value })} />
      </label>
      <div className="sub-head">
        <span>{t.projects}{r.projects.length > 0 && <span className="count"> {r.projects.length}</span>}</span>
        <button type="button" className="text-link" onClick={() => onChange({ ...r, projects: [...r.projects, emptyProject()] })}>{t.addProject}</button>
      </div>
      {r.projects.map((p, i) => (
        <ProjectEntry key={i} p={p} opts={opts} mySkills={mySkills}
          onChange={(np) => onChange({ ...r, projects: replaceAt(r.projects, i, np) })}
          onRemove={() => onChange({ ...r, projects: without(r.projects, i) })} />
      ))}
      <button type="button" className="text-link danger" onClick={onRemove}>{t.removeRole}</button>
    </div>
  )
}

function CareerEntry({ c, opts, mySkills, onChange, onRemove }: {
  c: Career; opts: ProfileOptions; mySkills: string[]; onChange: (c: Career) => void; onRemove: () => void
}) {
  return (
    <div className="entry">
      <div className="row2">
        <label className="field"><span>{t.company}</span>
          <input value={c.company} onChange={(e) => onChange({ ...c, company: e.target.value })} />
        </label>
        <Select label={t.industry} value={c.industry} options={opts.industries} onChange={(industry) => onChange({ ...c, industry })} />
      </div>
      <Period start={c.start} end={c.end} onChange={(start, end) => onChange({ ...c, start, end })} />
      <label className="field"><span>{t.position}</span>
        <input value={c.title} placeholder={t.positionPlaceholder} onChange={(e) => onChange({ ...c, title: e.target.value })} />
      </label>
      <div className="sub-head">
        <span>{t.roles}{c.roles.length > 0 && <span className="count"> {c.roles.length}</span>}</span>
        <button type="button" className="text-link" onClick={() => onChange({ ...c, roles: [...c.roles, emptyRole()] })}>{t.addRole}</button>
      </div>
      <p className="note">{t.rolesHelp}</p>
      {c.roles.map((r, i) => (
        <RoleEntry key={i} r={r} opts={opts} mySkills={mySkills}
          onChange={(nr) => onChange({ ...c, roles: replaceAt(c.roles, i, nr) })}
          onRemove={() => onChange({ ...c, roles: without(c.roles, i) })} />
      ))}
      <button type="button" className="text-link danger" onClick={onRemove}>{t.removeCareer}</button>
    </div>
  )
}

export function Profile({ options, skillOptions, panel = false }: {
  options?: ProfileOptions
  skillOptions: SkillOption[]
  panel?: boolean
}) {
  const [profile, setProfile] = useState<P>(emptyProfile)
  const [version, setVersion] = useState(0)
  const [skill, setSkill] = useState('')
  const [skillMsg, setSkillMsg] = useState('')
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

  const names = useMemo(() => Object.fromEntries((options?.roles ?? []).map((r) => [r.id, r.name])), [options])
  const counts = useMemo(() => new Map(skillOptions.map((s) => [s.name.toLowerCase(), s])), [skillOptions])
  if (!options) return <div className="page"><p className="empty">{copy.load.failed}</p></div>
  const opts = options

  const edit = (p: P) => {
    setProfile(p)
    if (state === 'saved' || state === 'failed') setState('idle')
  }
  const [total, dataYears] = careerTotals(profile)
  const mySkills = profile.skills.map((s) => s.name)

  async function save() {
    setState('saving')
    const next = version + 1
    const ok = await saveProfile(profile, next)
    if (ok) setVersion(next)
    setState(ok ? 'saved' : 'failed')
  }

  function addSkill() {
    const found = counts.get(skill.trim().toLowerCase())
    if (!skill.trim()) return
    if (!found) {
      setSkillMsg(t.notInList)
      return
    }
    if (!mySkills.includes(found.name)) edit({ ...profile, skills: [...profile.skills, { name: found.name, level: 0 }] })
    setSkill('')
    setSkillMsg('')
  }
  function onSkillKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault()
      addSkill()
    }
  }

  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && (
        <div className="topbar">
          <button type="button" className="icon-btn" aria-label={copy.job.back} onClick={() => goBack(href.admin)}>‹</button>
        </div>
      )}
      <header className="page-head">
        <h1>{t.title}</h1>
        <div className="page-sub">{[profile.careers.length > 0 && t.sub(yearsText(total), yearsText(dataYears)), version > 0 && `v${version}`].filter(Boolean).join(' · ')}</div>
      </header>

      {profile.careers.length > 0 && (
        <section className="section">
          <SectionTitle>{t.roleYears}</SectionTitle>
          <div className="chips wrap small">
            {roleYears(profile, names).map(([n, y]) => <span key={n} className="chip">{n} {t.years(yearsText(y))}</span>)}
          </div>
          <p className="note">{t.roleYearsNote}</p>
        </section>
      )}

      <section className="section form">
        <SectionTitle>{t.targetRoles}</SectionTitle>
        <div className="chips wrap">
          {opts.roles.filter((r) => r.id !== 'other').map((r) => {
            const on = profile.targetRoles.includes(r.id)
            return (
              <button key={r.id} type="button" className={on ? 'chip selected' : 'chip'} aria-pressed={on}
                onClick={() => edit({ ...profile, targetRoles: on ? profile.targetRoles.filter((x) => x !== r.id) : [...profile.targetRoles, r.id] })}>
                {r.name}
              </button>
            )
          })}
        </div>
      </section>

      <section className="section form">
        <SectionTitle right={<button type="button" className="text-link" onClick={() => edit({ ...profile, careers: [...profile.careers, emptyCareer()] })}>{t.addCareer}</button>}>
          {t.careers}
        </SectionTitle>
        {profile.careers.map((c, i) => (
          <CareerEntry key={i} c={c} opts={opts} mySkills={mySkills}
            onChange={(nc) => edit({ ...profile, careers: replaceAt(profile.careers, i, nc) })}
            onRemove={() => edit({ ...profile, careers: without(profile.careers, i) })} />
        ))}
      </section>

      <section className="section form">
        <SectionTitle>{t.skills}</SectionTitle>
        <p className="note">{t.skillsHelp}</p>
        <div className="levels-legend">
          {opts.skill_levels.map((l) => <span key={l.level}><b>{l.level}</b> {l.name}</span>)}
        </div>
        {profile.skills.map((s, i) => (
          <div key={s.name} className="skill-row">
            <span className="skill-name">{s.name}{counts.get(s.name.toLowerCase()) && <span className="count"> {t.skillCount(counts.get(s.name.toLowerCase())!.count)}</span>}</span>
            <div className="level-pick" role="radiogroup" aria-label={`${s.name} ${t.skills}`}>
              {opts.skill_levels.map((l) => (
                <button key={l.level} type="button" role="radio" aria-checked={s.level === l.level} title={`${l.name}: ${l.desc}`}
                  className={s.level === l.level ? 'on' : ''}
                  onClick={() => edit({ ...profile, skills: replaceAt(profile.skills, i, { ...s, level: l.level }) })}>{l.level}</button>
              ))}
            </div>
            <button type="button" className="text-link danger" aria-label={`${s.name} ${t.remove}`}
              onClick={() => edit({ ...profile, skills: without(profile.skills, i) })}>×</button>
          </div>
        ))}
        {profile.skills.some((s) => !s.level) && <p className="note urgent">{t.levelUnset}</p>}
        <div className="inline-add">
          <input value={skill} list="skill-options" placeholder={t.skillPlaceholder}
            onChange={(e) => { setSkill(e.target.value); setSkillMsg('') }} onKeyDown={onSkillKey} />
          <button type="button" className="btn" onClick={addSkill}>{t.add}</button>
        </div>
        <datalist id="skill-options">
          {skillOptions.filter((o) => !mySkills.includes(o.name)).map((o) => <option key={o.name} value={o.name}>{t.skillCount(o.count)}</option>)}
        </datalist>
        {skillMsg && <p className="note urgent">{skillMsg}</p>}
      </section>

      <section className="section form">
        <SectionTitle>{t.education}</SectionTitle>
        <div className="row2">
          <Select label={t.degree} value={profile.education.degree} options={asOptions(opts.degrees)}
            onChange={(degree) => edit({ ...profile, education: { ...profile.education, degree } })} />
          <Select label={t.majorGroup} value={profile.education.majorGroup} options={asOptions(opts.major_groups)}
            onChange={(majorGroup) => edit({ ...profile, education: { ...profile.education, majorGroup } })} />
        </div>
        <label className="field"><span>{t.major}</span>
          <input value={profile.education.major} onChange={(e) => edit({ ...profile, education: { ...profile.education, major: e.target.value } })} />
        </label>
        <Select label={t.english} value={profile.english} options={asOptions(opts.english)} onChange={(english) => edit({ ...profile, english })} />
        <div className="sub-head">
          <span>{t.certs}</span>
          <button type="button" className="text-link" onClick={() => edit({ ...profile, certs: [...profile.certs, { name: '', year: '' }] })}>{t.add}</button>
        </div>
        {profile.certs.map((c, i) => (
          <div key={i} className="row2 cert">
            <label className="field"><span>{t.certName}</span>
              <input value={c.name} onChange={(e) => edit({ ...profile, certs: replaceAt(profile.certs, i, { ...c, name: e.target.value }) })} />
            </label>
            <label className="field"><span>{t.certYear}</span>
              <input value={c.year} inputMode="numeric" onChange={(e) => edit({ ...profile, certs: replaceAt(profile.certs, i, { ...c, year: e.target.value }) })} />
            </label>
            <button type="button" className="text-link danger" onClick={() => edit({ ...profile, certs: without(profile.certs, i) })}>{t.remove}</button>
          </div>
        ))}
      </section>

      <div className="savebar">
        {state === 'saved' && <span className="note">{t.saved}</span>}
        {state === 'failed' && <span className="note urgent">{t.failed}</span>}
        <button type="button" className="btn primary" disabled={state === 'loading' || state === 'saving'} onClick={save}>{t.save}</button>
      </div>
    </div>
  )
}
