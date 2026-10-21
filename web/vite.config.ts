import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// 개발할 때만 로컬 화면용 파일을 내준다. 빌드 결과(공개되는 화면 코드)에는 공고 데이터가 들어가지 않는다.
function devScreenFile(): Plugin {
  const file = resolve(process.env.DEV_SCREEN_FILE ?? '../.dev-data/screen.json.gz')
  const dir = resolve(file, '..')
  return {
    name: 'dev-screen-file',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__dev/screen.json.gz', (_req, res) => {
        if (!existsSync(file)) {
          res.statusCode = 404
          res.end(`화면용 파일이 없어요: ${file} (uv run jobpost screen --out ${file})`)
          return
        }
        res.setHeader('Content-Type', 'application/octet-stream')
        res.end(readFileSync(file))
      })
      // 매칭 결과와 프로필(로그인 없이 화면을 볼 때)
      server.middlewares.use('/__dev/json', (req, res) => {
        const name = (req.url ?? '').replace(/^\//, '')
        const path = resolve(dir, name)
        if (!/^(matches|profile)\.json$/.test(name) || !existsSync(path)) {
          res.statusCode = 404
          res.end()
          return
        }
        res.setHeader('Content-Type', 'application/json')
        res.end(readFileSync(path))
      })
      server.middlewares.use('/__dev/companies.json.gz', (_req, res) => {
        const path = resolve(dir, 'companies.json.gz')
        if (!existsSync(path)) {
          res.statusCode = 404
          res.end()
          return
        }
        res.setHeader('Content-Type', 'application/octet-stream')
        res.end(readFileSync(path))
      })
      server.middlewares.use('/__dev/bodies', (req, res) => {
        const name = (req.url ?? '').replace(/^\//, '')
        const path = resolve(dir, 'bodies', name)
        if (!/^[0-9a-f]{2}\.json\.gz$/.test(name) || !existsSync(path)) {
          res.statusCode = 404
          res.end()
          return
        }
        res.setHeader('Content-Type', 'application/octet-stream')
        res.end(readFileSync(path))
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), devScreenFile()],
  // kakao.html: 카톡 연결 때 카카오가 인가 코드를 붙여 돌려보내는 화면(앱을 불러오지 않는다)
  build: { rollupOptions: { input: { main: 'index.html', kakao: 'kakao.html' } } },
})
