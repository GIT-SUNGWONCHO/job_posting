export function Later({ title, text }: { title: string; text: string }) {
  return (
    <div className="page">
      <header className="page-head"><h1>{title}</h1></header>
      <p className="empty">{text}</p>
    </div>
  )
}
