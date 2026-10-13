import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// 개발할 때만 로컬 화면용 파일을 내준다. 빌드 결과(공개되는 화면 코드)에는 공고 데이터가 들어가지 않는다.
function devScreenFile(): Plugin {
  const file = resolve(process.env.DEV_SCREEN_FILE ?? '../.dev-data/screen.json.gz')
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
    },
  }
}

export default defineConfig({
  plugins: [react(), devScreenFile()],
})
