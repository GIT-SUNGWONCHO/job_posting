import { Fragment, useEffect, useRef, useState } from 'react'
import { copy } from '../copy'
import { SourceSheet } from '../components/SourceSheet'
import { BACK_ICON, RIGHT_ICON, SectionTitle } from '../components/ui'
import { dateText } from '../lib/format'
import { loadNote, type Note, type NoteBlock, type NoteSection } from '../lib/notes'
import { goBack, href } from '../lib/route'
import type { Screen } from '../lib/types'

const t = copy.note

// 내 리서치 노트(앱 안 화면): 회사 · "내 리서치 노트 | 업데이트" · 기준 공고 → 요약 → 섹션 탭(누르면 그 섹션으로).
// 한 화면을 내려 읽는다. 출처는 섹션 제목 오른쪽 "출처" 시트. 블록 형식은 lib/notes.ts
export function NotePage({ screen, companyKey, section }: { screen: Screen; companyKey: string; section: number }) {
  const [state, setState] = useState<{ key: string; note: Note | null } | null>(null)
  useEffect(() => {
    let alive = true
    loadNote(companyKey).then((n) => alive && setState({ key: companyKey, note: n }), () => alive && setState({ key: companyKey, note: null }))
    return () => {
      alive = false
    }
  }, [companyKey])
  const note = state?.key === companyKey ? state.note : undefined
  const name = screen.companies[companyKey]?.name ?? companyKey
  return (
    <div className="page detail note-page">
      <div className="topbar">
        <button type="button" className="icon-btn" aria-label={copy.common.back} onClick={() => goBack(href.company(companyKey))}>{BACK_ICON}</button>
      </div>
      {note === undefined && <p className="empty">{copy.load.loading}</p>}
      {note === null && (
        <>
          <header className="detail-head"><h1>{name}</h1></header>
          <p className="empty">{t.none}</p>
        </>
      )}
      {note && <NoteBody note={note} section={section} screen={screen} />}
    </div>
  )
}

function NoteBody({ note, section, screen }: { note: Note; section: number; screen: Screen }) {
  const refs = useRef<(HTMLElement | null)[]>([])
  const [active, setActive] = useState(Math.max(section, 0))
  const [sheet, setSheet] = useState<NoteSection | null>(null)
  // 회사 화면에서 섹션 줄을 눌러 들어오면 그 섹션으로
  useEffect(() => {
    if (section >= 0) refs.current[section]?.scrollIntoView({ block: 'start' })
  }, [section])
  // 지금 보는 섹션의 탭에 밑줄(탭 줄 바로 아래를 지난 마지막 섹션)
  useEffect(() => {
    const onScroll = () => {
      const top = 120
      let cur = 0
      refs.current.forEach((el, i) => { if (el && el.getBoundingClientRect().top <= top) cur = i })
      setActive(cur)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  const posting = note.posting
  const inApp = posting?.id && screen.postings.some((p) => p.id === posting.id)
  return (
    <>
      <header className="detail-head note-head">
        <h1>{note.name}</h1>
        <div className="intro-meta"><span>{t.title}</span><span className="sep" /><span>{t.updated(dateText(note.updated))}</span></div>
      </header>
      {posting && (
        <a className="note-posting" href={inApp ? href.job(posting.id!) : posting.url ?? undefined}
          target={inApp ? undefined : '_blank'} rel={inApp ? undefined : 'noreferrer noopener'}>
          <span className="note-posting-main"><span className="muted">{t.posting}</span><b>{posting.title}</b></span>
          {posting.deadline && <span className="muted">{t.deadline(dateText(posting.deadline))}</span>}
          {inApp ? RIGHT_ICON : <span className="muted">↗</span>}
        </a>
      )}
      <section className="section note-summary">
        <SectionTitle>{t.summary}</SectionTitle>
        <Facts items={note.summary} />
      </section>
      <nav className="ntabs" aria-label={t.sections}>
        {note.sections.map((s, i) => (
          <button key={s.title} type="button" className={i === active ? 'on' : ''} aria-current={i === active ? 'true' : undefined}
            onClick={() => refs.current[i]?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{s.title}</button>
        ))}
      </nav>
      {note.sections.map((s, i) => (
        <section key={s.title} className="section note-sec" ref={(el) => { refs.current[i] = el }}>
          <SectionTitle right={s.sources.length > 0 && (
            <button type="button" className="src-btn" onClick={() => setSheet(s)}>{copy.common.source}</button>
          )}>{s.title}</SectionTitle>
          {s.blocks.map((b, j) => <Block key={j} b={b} />)}
        </section>
      ))}
      {sheet && <SourceSheet title={t.sourceOf(sheet.title)} items={sheet.sources} onClose={() => setSheet(null)} />}
    </>
  )
}

function Facts({ items }: { items: string[] }) {
  return <ul className="facts">{items.map((x) => <li key={x}>{x}</li>)}</ul>
}

/** 블록 하나: 제목(있으면) + 정해진 모양 */
function Block({ b }: { b: NoteBlock }) {
  return (
    <div className="note-block">
      {b.title && <h3 className="h3">{b.title}</h3>}
      <BlockBody b={b} />
    </div>
  )
}

const jo = (v: number) => (v >= 10000 ? `${(v / 10000).toFixed(2)}조` : `${v.toLocaleString()}억`)

function BlockBody({ b }: { b: NoteBlock }) {
  switch (b.t) {
    case 'kv':
      return (
        <div className="kv2 note-kv">
          {b.rows.map(([k, v, when]) => (
            <Fragment key={k}><span className="k">{k}</span><span className="v">{v}{when && <span className="when">{when}</span>}</span></Fragment>
          ))}
        </div>
      )
    case 'sub':
      return <h3 className="h3">{b.text}</h3>
    case 'facts':
      return <Facts items={b.items} />
    case 'table': {
      const cols = b.rows[0]?.length ?? 1
      const style = { gridTemplateColumns: cols === 2 ? '104px minmax(0, 1fr)' : `minmax(0, 1fr) repeat(${cols - 1}, auto)` }
      return (
        <div className={cols === 2 ? 'note-table two' : 'note-table'} style={style} role="table">
          {b.head?.map((h, i) => <span key={h} className={i > 0 ? 'th num' : 'th'}>{h}</span>)}
          {b.rows.map((r, ri) => r.map((cell, ci) => (
            <span key={`${ri}-${ci}`} className={[ci > 0 && cols > 2 ? 'num' : '', ri === b.strong ? 'strong' : '', cols === 2 && ci === 0 ? 'k' : ''].filter(Boolean).join(' ')}>{cell}</span>
          )))}
        </div>
      )
    }
    case 'timeline':
      return (
        <div className="note-timeline">
          {b.items.map(([when, title, desc], i) => (
            <Fragment key={`${when}-${title}`}>
              <span className={i === 0 ? 'when on' : 'when'}>{when}</span>
              <span className="what"><b>{title}</b>{desc && <span>{desc}</span>}</span>
            </Fragment>
          ))}
        </div>
      )
    case 'stack': {
      const max = Math.max(...b.rows.map(([, a, c]) => a + c), 1)
      return (
        <>
          <div className="note-bars">
            {b.rows.map(([label, a, c]) => (
              <Fragment key={label}>
                <span className={label === b.on ? 'label on' : 'label'}>{label}</span>
                <span className="bar-cell">
                  <span className="nbar" role="img" aria-label={`${label} ${b.series[0]} ${jo(a)}, ${b.series[1]} ${jo(c)}`}>
                    <i className="s1" style={{ width: `${(a / max) * 100}%` }} /><i className="s2" style={{ width: `${(c / max) * 100}%` }} />
                  </span>
                  <span className="bar-note">{b.series[0].replace('손익', '')} {jo(a)} · {b.series[1].replace('손익', '')} {jo(c)}</span>
                </span>
              </Fragment>
            ))}
          </div>
          <Legend series={b.series} />
        </>
      )
    }
    case 'mix':
      return (
        <>
          <div className="note-bars wide">
            {b.rows.map(([label, ...parts]) => (
              <Fragment key={label}>
                <span className="label">{label}</span>
                <span className="bar-cell">
                  <span className="nbar" role="img" aria-label={`${label} ${b.series.map((s, i) => `${s} ${parts[i]}%`).join(', ')}`}>
                    {parts.map((p, i) => <i key={i} className={`s${i + 1}`} style={{ width: `${p}%` }} />)}
                  </span>
                  <span className="bar-note">{b.series.map((s, i) => `${s} ${parts[i]}%`).join(' · ')}</span>
                </span>
              </Fragment>
            ))}
          </div>
          <Legend series={b.series} />
        </>
      )
    case 'steps':
      return (
        <div className="note-steps">
          {b.items.map(([name, desc, ai], i) => (
            <div key={name} className="step">
              <span className="step-n">{i + 1}</span>
              <span className="step-main"><span><b>{name}</b> <span className="muted">{desc}</span></span><span><b className="ai">AI</b> {ai}</span></span>
            </div>
          ))}
        </div>
      )
    case 'quote':
      return <blockquote className="note-quote"><span>{b.text}</span><span className="muted">{b.by}</span></blockquote>
    case 'path':
      return (
        <div className="note-path">
          {b.items.map((x, i) => <Fragment key={x}>{i > 0 && RIGHT_ICON}<span className={i === b.items.length - 1 ? 'last' : ''}>{x}</span></Fragment>)}
          {b.note && <span className="muted small">{b.note}</span>}
        </div>
      )
    case 'cards':
      return (
        <div className="note-cards">
          {b.items.map(([label, value, on]) => (
            <span key={label} className={on ? 'card on' : 'card'}><span>{label}</span><b>{value}</b></span>
          ))}
        </div>
      )
  }
}

function Legend({ series }: { series: string[] }) {
  return <div className="legend">{series.map((s, i) => <span key={s}><i className={`sw s${i + 1}`} />{s}</span>)}</div>
}
