import './styles/tokens.css'
import './styles/app.css'
import { copy } from './copy'

// 카톡 연결 화면(/kakao, 파일은 kakao.html): 카카오 로그인 뒤 돌아오는 주소(config/notify.yaml redirect_path).
// 로그인·데이터를 불러오지 않고 주소에 붙어 온 인가 코드만 보여준다. 코드는 GitHub Actions > kakao에 넣는다(docs/setup.md "4. 카카오").
const t = copy.kakao

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (cls) node.className = cls
  if (text !== undefined) node.textContent = text
  return node
}

const params = new URLSearchParams(window.location.search)
const code = params.get('code')
const error = params.get('error_description') ?? params.get('error')

const page = el('main', 'page')
const head = el('div', 'page-head')
head.append(el('h1', undefined, t.title))
page.append(head)

const body = el('section', 'section kakao')
if (code) {
  const steps = el('ol', 'kakao-steps')
  for (const s of t.steps) steps.append(el('li', undefined, s))
  const box = el('div', 'kakao-code')
  const value = el('code', undefined, code)
  value.setAttribute('aria-label', t.code)
  const btn = el('button', 'btn primary', t.copy)
  btn.type = 'button'
  btn.onclick = () => {
    navigator.clipboard.writeText(code).then(
      () => { btn.textContent = t.copied },
      () => window.getSelection()?.selectAllChildren(value),
    )
  }
  box.append(value, btn)
  body.append(steps, box, el('p', 'note', t.once))
} else {
  body.append(el('p', 'note urgent', error ? t.failed(error) : t.none))
}
const back = el('a', 'btn', t.dashboard)
back.href = '/'
body.append(back)
page.append(body)
document.getElementById('root')!.append(page)
