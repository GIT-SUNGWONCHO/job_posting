import './styles/tokens.css'
import './styles/app.css'
import { copy } from './copy'

// 카톡 연결 화면(/kakao, 파일은 kakao.html): 카카오 로그인 뒤 돌아오는 주소(config/notify.yaml redirect_path).
// 로그인·데이터를 불러오지 않는다. 코드가 없으면 REST API 키를 받아 카카오 인가 주소로 보내고(키는 저장하지 않음),
// 돌아오면 주소에 붙어 온 인가 코드를 보여준다. 코드는 GitHub Actions > kakao에 넣는다(docs/setup.md "4. 카카오").
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
  if (error) body.append(el('p', 'note urgent', t.failed(error)))
  body.append(connectForm())
}

/** REST API 키로 카카오 인가 주소를 만든다. 주소를 손으로 고치다 <>나 다른 키가 들어가 KOE101이 나던 것을 막는다. */
function connectForm(): HTMLFormElement {
  const form = el('form', 'kakao')
  const label = el('label', 'kakao-key')
  const input = el('input')
  input.name = 'key'
  input.autocomplete = 'off'
  input.spellcheck = false
  label.append(el('span', undefined, t.keyLabel), input)
  const warn = el('p', 'note urgent')
  warn.hidden = true
  const btn = el('button', 'btn primary', t.connect)
  btn.type = 'submit'
  form.append(el('p', 'note', t.none), label, el('p', 'note', t.keyHint), warn, btn)
  form.onsubmit = (e) => {
    e.preventDefault()
    const key = input.value.replace(/[<>\s]/g, '')
    if (!/^[0-9a-f]{32}$/i.test(key)) {
      warn.textContent = t.keyWrong
      warn.hidden = false
      return
    }
    const q = new URLSearchParams({
      response_type: 'code', scope: 'talk_message', client_id: key,
      redirect_uri: window.location.origin + window.location.pathname,
    })
    window.location.href = `https://kauth.kakao.com/oauth/authorize?${q}`
  }
  return form
}
const back = el('a', 'btn', t.dashboard)
back.href = '/'
body.append(back)
page.append(body)
document.getElementById('root')!.append(page)
