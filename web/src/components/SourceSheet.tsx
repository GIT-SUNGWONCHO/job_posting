import { useEffect } from 'react'

/** 출처 시트에 담는 줄: 이름 · 무엇에 썼는지(있으면) · 원문 */
export interface SourceItem { title: string; detail?: string; url?: string | null }

/** 출처 시트: 아래에서 올라오고, 줄마다 원문으로(↗) */
export function SourceSheet({ title, items, onClose }: { title: string; items: SourceItem[]; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet source-sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="grip" aria-hidden="true" />
        <h2>{title}</h2>
        {items.map((it) => {
          const inner = <><span className="src-main"><b>{it.title}</b>{it.detail && <span>{it.detail}</span>}</span>{it.url && <span className="muted">↗</span>}</>
          return it.url
            ? <a key={it.title + (it.url ?? '')} className="src-row" href={it.url} target="_blank" rel="noreferrer noopener">{inner}</a>
            : <div key={it.title + (it.url ?? '')} className="src-row">{inner}</div>
        })}
      </div>
    </div>
  )
}
