import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react'
import { copy } from '../copy'
import { BACK_ICON, DOWN_ICON, SEARCH_ICON, SectionTitle } from '../components/ui'
import {
  careerTotals, durationText, emptyCareer, emptyProfile, emptyProject, emptyRole, loadProfile, months, periodText, roleLabel,
  roleYears, saveProfile, type Career, type Profile as P, type Project, type Role,
} from '../lib/profile'
import { goBack, href } from '../lib/route'
import type { ProfileOptions, SkillOption } from '../lib/types'

const t = copy.profile

const replaceAt = <T,>(list: T[], i: number, v: T): T[] => list.map((x, j) => (j === i ? v : x))
const without = <T,>(list: T[], i: number) => list.filter((_, j) => j !== i)
const asOptions = (xs: string[]) => xs.map((x) => ({ id: x, name: x }))
/** 최근 것이 위로(끝이 비면 지금) */
const byRecent = <X extends { start: string; end: string }>(a: X, b: X) => (b.end || '9999').localeCompare(a.end || '9999') || b.start.localeCompare(a.start)

const PENCIL = (
  <svg className="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></svg>
)

type Editing = { kind: 'career'; index: number } | { kind: 'skills' } | { kind: 'target' } | { kind: 'edu' }

// 프로필: 보기가 먼저, 덩어리마다 연필로 그 덩어리만 편집(경력은 회사 하나씩 한 페이지).
// 경력은 회사 > 직무(점과 세로선) > 프로젝트(회색 상자), 회사마다 프로젝트를 접는다. 저장하면 버전이 하나 오른다
export function Profile({ options, skillOptions, panel = false }: {
  options?: ProfileOptions
  skillOptions: SkillOption[]
  panel?: boolean
}) {
  const [profile, setProfile] = useState<P>(emptyProfile)
  const [version, setVersion] = useState(0)
  const [state, setState] = useState<'loading' | 'idle' | 'saving' | 'failed'>('loading')
  const [editing, setEditing] = useState<Editing | null>(null)

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
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [editing])

  if (!options) return <div className="page"><p className="empty">{copy.load.failed}</p></div>
  const opts = options

  async function save(next: P) {
    setState('saving')
    const v = version + 1
    const ok = await saveProfile(next, v)
    if (!ok) return setState('failed')
    setProfile(next)
    setVersion(v)
    setState('idle')
    setEditing(null)
  }
  const edit = {
    busy: state === 'saving',
    failed: state === 'failed',
    cancel: () => { setEditing(null); setState('idle') },
  }

  if (editing?.kind === 'career') {
    const isNew = editing.index < 0
    const career = isNew ? emptyCareer() : profile.careers[editing.index]
    return (
      <CareerEdit career={career} isNew={isNew} opts={opts} mySkills={profile.skills.map((s) => s.name)} {...edit}
        onSave={(c) => save({ ...profile, careers: isNew ? [...profile.careers, c] : replaceAt(profile.careers, editing.index, c) })}
        onDelete={() => save({ ...profile, careers: without(profile.careers, editing.index) })} />
    )
  }
  if (editing?.kind === 'skills') {
    return <SkillEdit skills={profile.skills} opts={opts} skillOptions={skillOptions} {...edit} onSave={(skills) => save({ ...profile, skills })} />
  }
  if (editing?.kind === 'target') {
    return <TargetEdit value={profile.targetRoles} opts={opts} {...edit} onSave={(targetRoles) => save({ ...profile, targetRoles })} />
  }
  if (editing?.kind === 'edu') {
    return <EduEdit profile={profile} opts={opts} {...edit} onSave={(p) => save({ ...profile, ...p })} />
  }
  return <ProfileView profile={profile} opts={opts} panel={panel} loading={state === 'loading'} onEdit={setEditing} />
}

function ProfileView({ profile, opts, panel, loading, onEdit }: {
  profile: P
  opts: ProfileOptions
  panel: boolean
  loading: boolean
  onEdit: (e: Editing) => void
}) {
  const names = useMemo(() => Object.fromEntries(opts.roles.map((r) => [r.id, r.name])), [opts])
  const industries = useMemo(() => Object.fromEntries(opts.industries.map((r) => [r.id, r.name])), [opts])
  const total = profile.careers.reduce((s, c) => s + months(c.start, c.end), 0)
  const [, dataYears] = careerTotals(profile)
  const careers = profile.careers.map((c, i) => ({ c, i })).sort((a, b) => byRecent(a.c, b.c))
  const pencil = (label: string, e: Editing) => (
    <button type="button" className="icon-btn edit-btn" aria-label={t.editOf(label)} onClick={() => onEdit(e)}>{PENCIL}</button>
  )
  const levels = [...opts.skill_levels].sort((a, b) => b.level - a.level)
  const unset = profile.skills.filter((s) => !s.level)
  return (
    <div className={panel ? 'page detail panel' : 'page detail'}>
      {!panel && (
        <div className="topbar">
          <button type="button" className="icon-btn" aria-label={copy.common.back} onClick={() => goBack(href.admin)}>{BACK_ICON}</button>
        </div>
      )}
      <header className="detail-head profile-head">
        <h1>{t.title}</h1>
        {loading ? <p className="note">{copy.load.loading}</p> : total > 0 && (
          <>
            <div className="total">{t.careerTotal} <b>{durationText(total)}</b></div>
            <div className="intro-meta wrap">
              {roleYears(profile, names).map(([n, y], i) => (
                <Fragment key={n}>{i > 0 && <span className="sep" />}<span>{n} {durationText(Math.round(y * 12))}</span></Fragment>
              ))}
            </div>
            {dataYears < total / 12 - 0.05 && <p className="note">{t.dataYears(durationText(Math.round(dataYears * 12)))}</p>}
          </>
        )}
      </header>

      <section className="section careers">
        <SectionTitle right={<button type="button" className="text-link" onClick={() => onEdit({ kind: 'career', index: -1 })}>{t.addShort}</button>}>
          {t.careers}
        </SectionTitle>
        {careers.length === 0 && !loading && <p className="note">{t.noCareers}</p>}
        {careers.map(({ c, i }, k) => (
          <CareerView key={i} c={c} names={names} industry={industries[c.industry]} openAtFirst={k === 0}
            edit={pencil(c.company || t.careers, { kind: 'career', index: i })} />
        ))}
      </section>

      <section className="section">
        <SectionTitle right={pencil(t.skills, { kind: 'skills' })}>{t.skills}</SectionTitle>
        {profile.skills.length === 0 ? <p className="note">{t.noSkills}</p> : (
          <div className="kv2 wide plain">
            {levels.map((l) => {
              const list = profile.skills.filter((s) => s.level === l.level)
              return list.length > 0 && <Fragment key={l.level}><span className="k">{l.name}</span><span className="v">{list.map((s) => s.name).join(' · ')}</span></Fragment>
            })}
            {unset.length > 0 && <><span className="k urgent">{t.levelUnsetShort}</span><span className="v">{unset.map((s) => s.name).join(' · ')}</span></>}
          </div>
        )}
      </section>

      <section className="section">
        <SectionTitle right={pencil(t.targetRoles, { kind: 'target' })}>{t.targetRoles}</SectionTitle>
        {profile.targetRoles.length === 0 ? <p className="note">{t.noTarget}</p>
          : <span className="v">{profile.targetRoles.map((r) => names[r] ?? r).join(' · ')}</span>}
      </section>

      <section className="section">
        <SectionTitle right={pencil(t.education, { kind: 'edu' })}>{t.education}</SectionTitle>
        <div className="kv2 wide plain">
          <span className="k">{t.degree}</span>
          <span className="v">{[profile.education.degree, profile.education.major || profile.education.majorGroup].filter(Boolean).join(' · ') || '-'}</span>
          <span className="k">{t.certs}</span>
          <span className="v">{profile.certs.filter((c) => c.name).map((c) => (c.year ? `${c.name} (${c.year})` : c.name)).join(', ') || '-'}</span>
          <span className="k">{t.english}</span>
          <span className="v">{profile.english || '-'}</span>
        </div>
      </section>
    </div>
  )
}

/** 회사 하나: 이름 · 직급 | 업종 · 기간, 직무는 점과 세로선(최근이 위), 프로젝트는 회색 상자(회사마다 접기) */
function CareerView({ c, names, industry, openAtFirst, edit }: {
  c: Career
  names: Record<string, string>
  industry?: string
  openAtFirst: boolean
  edit: ReactNode
}) {
  const [open, setOpen] = useState(openAtFirst)
  const roles = [...c.roles].sort(byRecent)
  const projectCount = c.roles.reduce((n, r) => n + r.projects.length, 0)
  return (
    <article className="career">
      <div className="career-head">
        <div className="career-title">
          <h3>{c.company || t.noCompany}</h3>
          <div className="intro-meta small">{[c.title, industry].filter(Boolean).map((x, i) => <Fragment key={x}>{i > 0 && <span className="sep" />}<span>{x}</span></Fragment>)}</div>
          <span className="muted-sm">{periodText(c.start, c.end, t.now)}</span>
        </div>
        {edit}
      </div>
      {roles.length > 0 && (
        <div className="tl-list">
          {roles.map((r, i) => (
            <div key={i} className="tl">
              <span className="tl-rail"><span className={!r.end ? 'dot now' : 'dot'} />{i < roles.length - 1 && <span className="rail" />}</span>
              <div className="tl-body">
                <div className="tl-head"><b>{roleLabel(r, names) || t.noRole}</b><span className="muted-sm">{periodText(r.start, r.end, t.present)}</span></div>
                {r.summary && <p className="role-summary">{r.summary}</p>}
                {open && r.projects.length > 0 && (
                  <div className="project-box">
                    {[...r.projects].sort(byRecent).map((p, j) => <ProjectView key={j} p={p} />)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {projectCount > 0 && (
        <button type="button" className="fold-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? t.foldProjects : t.unfoldProjects(projectCount)}<span className={open ? 'chev up' : 'chev'}>{DOWN_ICON}</span>
        </button>
      )}
    </article>
  )
}

function ProjectView({ p }: { p: Project }) {
  const lines = p.summary.split('\n').map((l) => l.replace(/^\s*[-•·]\s*/, '').trim()).filter(Boolean)
  return (
    <div className="project">
      <b>{p.title || t.noTitle}</b>
      <span className="muted-sm">{[periodText(p.start, p.end, t.present), p.part].filter(Boolean).join(' · ')}</span>
      {lines.length > 0 && <ul>{lines.map((l, i) => <li key={i}>{l}</li>)}</ul>}
      {p.skills.length > 0 && <span className="muted-sm">{p.skills.join(' · ')}</span>}
    </div>
  )
}

// ---------- 편집 페이지: 위 줄(취소 · 제목 · 저장)과 그 덩어리만 ----------

function EditTop({ title, busy, failed, onCancel, onSave }: { title: string; busy: boolean; failed: boolean; onCancel: () => void; onSave: () => void }) {
  return (
    <>
      <div className="topbar edit-top">
        <button type="button" className="text-link plain" onClick={onCancel}>{t.cancel}</button>
        <span className="edit-title">{title}</span>
        <button type="button" className="text-link" disabled={busy} onClick={onSave}>{busy ? t.saving : t.save}</button>
      </div>
      {failed && <p className="note urgent edit-note">{t.failed}</p>}
    </>
  )
}

interface EditProps { busy: boolean; failed: boolean; cancel: () => void }

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>
}

function Select({ label, value, options, onChange }: {
  label: string; value: string; options: { id: string; name: string }[]; onChange: (v: string) => void
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t.choose}</option>
        {options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </Field>
  )
}

function Period({ start, end, onChange }: { start: string; end: string; onChange: (start: string, end: string) => void }) {
  return (
    <div className="row2">
      <Field label={t.start}><input type="month" value={start} onChange={(e) => onChange(e.target.value, end)} /></Field>
      <Field label={t.endHint}><input type="month" value={end} onChange={(e) => onChange(start, e.target.value)} /></Field>
    </div>
  )
}

function CareerEdit({ career, isNew, opts, mySkills, busy, failed, cancel, onSave, onDelete }: EditProps & {
  career: Career
  isNew: boolean
  opts: ProfileOptions
  mySkills: string[]
  onSave: (c: Career) => void
  onDelete: () => void
}) {
  const [c, setC] = useState<Career>(career)
  const [confirm, setConfirm] = useState(false)
  const setRole = (i: number, r: Role) => setC({ ...c, roles: replaceAt(c.roles, i, r) })
  return (
    <div className="page detail edit-page">
      <EditTop title={isNew ? t.addCareerTitle : t.careerEdit} busy={busy} failed={failed} onCancel={cancel} onSave={() => onSave(c)} />
      <div className="edit-body">
        <Field label={t.company}><input value={c.company} onChange={(e) => setC({ ...c, company: e.target.value })} /></Field>
        <div className="row2">
          <Field label={t.position}><input value={c.title} placeholder={t.positionPlaceholder} onChange={(e) => setC({ ...c, title: e.target.value })} /></Field>
          <Select label={t.industry} value={c.industry} options={opts.industries} onChange={(industry) => setC({ ...c, industry })} />
        </div>
        <Period start={c.start} end={c.end} onChange={(start, end) => setC({ ...c, start, end })} />
      </div>
      <div className="band" />
      <div className="edit-body">
        <SectionTitle count={c.roles.length}>{t.role}</SectionTitle>
        <p className="note">{t.rolesHelp}</p>
        <div className="tl-list">
          {c.roles.map((r, i) => (
            <div key={i} className="tl">
              <span className="tl-rail"><span className={!r.end ? 'dot now' : 'dot'} />{i < c.roles.length - 1 && <span className="rail" />}</span>
              <div className="tl-body edit">
                <Select label={t.role} value={r.role} options={opts.roles} onChange={(role) => setRole(i, { ...r, role })} />
                {r.role === 'other' && <Field label={t.roleName}><input value={r.roleName ?? ''} onChange={(e) => setRole(i, { ...r, roleName: e.target.value })} /></Field>}
                <Period start={r.start} end={r.end} onChange={(start, end) => setRole(i, { ...r, start, end })} />
                <Field label={t.roleSummary}>
                  <textarea rows={2} value={r.summary} placeholder={t.roleSummaryPlaceholder} onChange={(e) => setRole(i, { ...r, summary: e.target.value })} />
                </Field>
                {r.projects.map((p, j) => (
                  <ProjectEdit key={j} n={j + 1} p={p} opts={opts} mySkills={mySkills}
                    onChange={(np) => setRole(i, { ...r, projects: replaceAt(r.projects, j, np) })}
                    onRemove={() => setRole(i, { ...r, projects: without(r.projects, j) })} />
                ))}
                <button type="button" className="text-link" onClick={() => setRole(i, { ...r, projects: [...r.projects, emptyProject()] })}>{t.addProject}</button>
                <button type="button" className="small-del" onClick={() => setC({ ...c, roles: without(c.roles, i) })}>{t.removeRole}</button>
              </div>
            </div>
          ))}
        </div>
        <button type="button" className="btn block" onClick={() => setC({ ...c, roles: [...c.roles, emptyRole()] })}>{t.addRole}</button>
        {!isNew && (confirm
          ? <div className="confirm-row"><span>{t.removeCareerAsk}</span><button type="button" className="text-link danger-strong" disabled={busy} onClick={onDelete}>{t.removeCareer}</button></div>
          : <button type="button" className="text-link danger-strong center" onClick={() => setConfirm(true)}>{t.removeCareer}</button>)}
      </div>
    </div>
  )
}

function ProjectEdit({ n, p, opts, mySkills, onChange, onRemove }: {
  n: number; p: Project; opts: ProfileOptions; mySkills: string[]; onChange: (p: Project) => void; onRemove: () => void
}) {
  return (
    <div className="project-edit">
      <div className="project-edit-head"><span>{t.projectN(n)}</span><button type="button" className="small-del" onClick={onRemove}>{t.remove}</button></div>
      <Field label={t.projectTitle}><input value={p.title} onChange={(e) => onChange({ ...p, title: e.target.value })} /></Field>
      <Period start={p.start} end={p.end} onChange={(start, end) => onChange({ ...p, start, end })} />
      <Select label={t.part} value={p.part} options={asOptions(opts.project_parts)} onChange={(part) => onChange({ ...p, part })} />
      <Field label={t.summary}>
        <textarea rows={4} value={p.summary} placeholder={t.summaryPlaceholder} onChange={(e) => onChange({ ...p, summary: e.target.value })} />
      </Field>
      <div className="field"><span>{t.projectSkills}</span>
        {mySkills.length ? (
          <div className="chips wrap">
            {mySkills.map((s) => {
              const on = p.skills.includes(s)
              return (
                <button key={s} type="button" className={on ? 'chip selected' : 'chip'} aria-pressed={on}
                  onClick={() => onChange({ ...p, skills: on ? p.skills.filter((x) => x !== s) : [...p.skills, s] })}>{s}</button>
              )
            })}
          </div>
        ) : <span className="note">{t.projectSkillsEmpty}</span>}
      </div>
    </div>
  )
}

/** 스킬 편집: 찾아서 추가(공고에 나온 스킬만), 숙련도는 한 줄에 네 칸, 공고 수는 보이지 않는다 */
function SkillEdit({ skills, opts, skillOptions, busy, failed, cancel, onSave }: EditProps & {
  skills: P['skills']
  opts: ProfileOptions
  skillOptions: SkillOption[]
  onSave: (s: P['skills']) => void
}) {
  const [list, setList] = useState(skills)
  const [q, setQ] = useState('')
  const mine = new Set(list.map((s) => s.name))
  const query = q.trim().toLowerCase()
  const found = query ? skillOptions.filter((o) => o.name.toLowerCase().includes(query)).slice(0, 6) : []
  const levels = [...opts.skill_levels].sort((a, b) => a.level - b.level)
  return (
    <div className="page detail edit-page">
      <EditTop title={t.skillEdit} busy={busy} failed={failed} onCancel={cancel} onSave={() => onSave(list)} />
      <div className="edit-body">
        <label className="search-box">{SEARCH_ICON}<input type="search" value={q} placeholder={t.skillPlaceholder} aria-label={t.skillPlaceholder} onChange={(e) => setQ(e.target.value)} /></label>
        {query && (
          <div className="pick-list">
            {found.map((o) => (
              <div key={o.name} className="pick-row">
                <b>{o.name}</b>
                {mine.has(o.name) ? <span className="muted-sm">{t.added}</span>
                  : <button type="button" className="text-link" onClick={() => { setList([...list, { name: o.name, level: 0 }]); setQ('') }}>{t.addOne}</button>}
              </div>
            ))}
            {found.length === 0 && <p className="note pick-empty">{t.notInList}</p>}
          </div>
        )}
        <SectionTitle count={list.length}>{t.mySkills}</SectionTitle>
        <div className="level-guide">{levels.map((l) => <Fragment key={l.level}><b>{l.name}</b><span>{l.desc}</span></Fragment>)}</div>
        <div className="skill-rows">
          {list.map((s, i) => (
            <div key={s.name} className="skill-row">
              <span className="skill-name">{s.name}</span>
              <div className="seg-pick" role="radiogroup" aria-label={t.levelOf(s.name)}>
                {levels.map((l) => (
                  <button key={l.level} type="button" role="radio" aria-checked={s.level === l.level} className={s.level === l.level ? 'on' : ''}
                    onClick={() => setList(replaceAt(list, i, { ...s, level: l.level }))}>{l.name}</button>
                ))}
              </div>
              <button type="button" className="icon-btn x-btn" aria-label={t.removeOf(s.name)} onClick={() => setList(without(list, i))}>×</button>
            </div>
          ))}
        </div>
        {list.some((s) => !s.level) && <p className="note urgent">{t.levelUnset}</p>}
      </div>
    </div>
  )
}

function TargetEdit({ value, opts, busy, failed, cancel, onSave }: EditProps & { value: string[]; opts: ProfileOptions; onSave: (v: string[]) => void }) {
  const [v, setV] = useState(value)
  return (
    <div className="page detail edit-page">
      <EditTop title={t.targetRoles} busy={busy} failed={failed} onCancel={cancel} onSave={() => onSave(v)} />
      <div className="edit-body">
        <p className="note">{t.targetHelp}</p>
        <div className="chips wrap">
          {opts.roles.filter((r) => r.id !== 'other').map((r) => {
            const on = v.includes(r.id)
            return (
              <button key={r.id} type="button" className={on ? 'chip selected' : 'chip'} aria-pressed={on}
                onClick={() => setV(on ? v.filter((x) => x !== r.id) : [...v, r.id])}>{r.name}</button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function EduEdit({ profile, opts, busy, failed, cancel, onSave }: EditProps & {
  profile: P
  opts: ProfileOptions
  onSave: (p: Pick<P, 'education' | 'certs' | 'english'>) => void
}) {
  const [edu, setEdu] = useState(profile.education)
  const [certs, setCerts] = useState(profile.certs)
  const [english, setEnglish] = useState(profile.english)
  return (
    <div className="page detail edit-page">
      <EditTop title={t.education} busy={busy} failed={failed} onCancel={cancel} onSave={() => onSave({ education: edu, certs, english })} />
      <div className="edit-body">
        <div className="row2">
          <Select label={t.degree} value={edu.degree} options={asOptions(opts.degrees)} onChange={(degree) => setEdu({ ...edu, degree })} />
          <Select label={t.majorGroup} value={edu.majorGroup} options={asOptions(opts.major_groups)} onChange={(majorGroup) => setEdu({ ...edu, majorGroup })} />
        </div>
        <Field label={t.major}><input value={edu.major} onChange={(e) => setEdu({ ...edu, major: e.target.value })} /></Field>
        <Select label={t.english} value={english} options={asOptions(opts.english)} onChange={setEnglish} />
        <SectionTitle right={<button type="button" className="text-link" onClick={() => setCerts([...certs, { name: '', year: '' }])}>{t.addShort}</button>}>{t.certs}</SectionTitle>
        {certs.map((c, i) => (
          <div key={i} className="row2 cert">
            <Field label={t.certName}><input value={c.name} onChange={(e) => setCerts(replaceAt(certs, i, { ...c, name: e.target.value }))} /></Field>
            <Field label={t.certYear}><input value={c.year} inputMode="numeric" onChange={(e) => setCerts(replaceAt(certs, i, { ...c, year: e.target.value }))} /></Field>
            <button type="button" className="small-del" onClick={() => setCerts(without(certs, i))}>{t.remove}</button>
          </div>
        ))}
      </div>
    </div>
  )
}
