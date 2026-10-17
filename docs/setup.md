# 운영 설정

계정을 만들고 키를 넣는 순서. 키 값은 이 문서에도, 코드와 커밋에도 적지 않는다. 넣을 곳은 GitHub Secrets와 Cloudflare 빌드 변수뿐이다. 사람마다 받는 카카오 연결 토큰만 Supabase의 서버 전용 표에 둔다(아래 4).

## 1. Supabase (저장소, 로그인)

1. supabase.com에서 새 프로젝트를 만든다. 지역은 Northeast Asia (Seoul), 무료 등급.
2. **SQL Editor**에서 아래를 한 번 실행한다. 비공개 저장소 `screen`을 만들고, 로그인한 사람만 읽게 한다.

   ```sql
   insert into storage.buckets (id, name, public)
   values ('screen', 'screen', false)
   on conflict (id) do nothing;

   create policy "로그인한 사람은 화면용 파일을 읽는다"
   on storage.objects for select to authenticated
   using (bucket_id = 'screen');
   ```

   이어서 `supabase/migrations/` 폴더의 SQL 파일을 번호 순서대로 SQL Editor에서 실행한다(사람별 설정 표와 권한). 새 파일이 생기면 그것만 실행한다.

3. **Authentication**
   - 이메일 로그인을 켜 두고, 새 사용자 가입(Allow new users to sign up)은 **반드시** 끈다. publishable 키는 공개되는 값이라, 가입이 열려 있으면 누구나 가입해서 "로그인한 사람"이 될 수 있다.
   - Users에서 본인 이메일을 초대한다(지인도 여기서 초대). 초대 메일 링크는 보내는 순간의 Site URL로 돌아가므로, 아래 Site URL을 먼저 저장하고 초대한다.
   - 기본 메일 발송은 시간당 몇 통으로 제한된다. 지인을 여럿 초대할 때는 메일 발송 서비스(SMTP)를 따로 연결한다.
   - URL Configuration의 Site URL에 대시보드 주소(Cloudflare, 아래 2)를, Redirect URLs에 같은 주소와 `http://localhost:5173`을 넣는다.
4. **Project Settings > API Keys**에서 두 값을 확인한다.
   - Project URL과 publishable key(`sb_publishable_…`): 화면에서 쓴다. 공개돼도 되는 키다.
   - secret key(`sb_secret_…`): 매일 수집 작업만 쓴다. 절대 화면이나 채팅에 붙이지 않는다.

## 1-1. 구글 로그인

로그인은 구글 계정으로 한다(이메일 링크는 예비). 구글 계정의 이메일이 Supabase에서 초대한 이메일과 같아야 들어올 수 있다.

1. console.cloud.google.com에서 새 프로젝트를 만든다(예: `careermap`).
2. **Google Auth Platform**(예전 이름 OAuth 동의 화면)을 시작한다.
   - 앱 이름 `careermap`, 지원 이메일은 본인, 대상(Audience)은 External.
   - 게시(Publish app)하지 않고 "테스트 중"으로 둔다. 게시하려면 홈페이지·개인정보처리방침 페이지가 필요해서다. 대신 대상(Audience) > 테스트 사용자에 쓸 사람의 구글 이메일을 넣는다(최대 100명).
   - 그래서 사람을 추가할 때는 **Supabase 초대**와 **구글 테스트 사용자** 두 곳에 같은 이메일을 넣는다. 처음 로그인할 때 "확인되지 않은 앱" 안내가 뜨면 계속을 누른다.
3. **Clients > Create client**: 종류는 Web application.
   - Authorized JavaScript origins: 대시보드 주소(`https://careermap-web.<계정>.workers.dev`)
   - Authorized redirect URIs: `https://<Supabase 프로젝트>.supabase.co/auth/v1/callback`
   - 만들면 Client ID와 Client secret이 나온다.
4. Supabase > Authentication > Sign In / Providers > **Google**을 켜고 Client ID와 Client secret을 붙여 넣고 저장한다. Client secret은 채팅이나 문서에 붙이지 않는다.
5. 대시보드에서 "Google로 로그인"을 눌러 확인한다. 초대 명단에 없는 구글 계정이면 "초대받은 계정만 들어올 수 있어요"가 뜬다.

로그인은 기기(브라우저)마다 한 번 한다. 한 번 들어오면 로그아웃할 때까지 유지된다.

## 2. Cloudflare Workers (화면)

Vercel과 같은 역할이다. GitHub 레포를 연결해 두면 main에 올릴 때마다 Cloudflare가 가져가 빌드하고 배포한다. 처음에는 Cloudflare Access(로그인 문)도 쓰려고 골랐는데, 로그인을 Supabase로 바꾼 뒤로는 화면 코드 호스팅만 한다. 2026.10 대시보드에는 Pages 대신 Workers 만들기("Create application")만 보여서 Workers 정적 사이트로 올린다. 설정은 `web/wrangler.jsonc`에 있다.

1. dash.cloudflare.com > Workers & Pages > Create application > GitHub 레포 가져오기.
   - GitHub 연결 창에서 "Only select repositories"로 이 레포만 허용한다.
2. 이름: `careermap-web`(`web/wrangler.jsonc`의 name과 같아야 한다). 주소는 `careermap-web.<계정>.workers.dev`가 된다.
3. 빌드 설정
   - Build command: `npm run build`
   - Deploy command: `npx wrangler deploy`(기본값 그대로)
   - Enable Preview builds: 끔. 매일 커밋되는 `data` 브랜치 때문에 쓸데없는 빌드가 돌지 않게 한다
   - Protect with Cloudflare Access: 끔(로그인은 Supabase)
   - Advanced settings > Path(root directory): `web`
   - Advanced settings > Build variables: `NODE_VERSION`=`22`, `VITE_SUPABASE_URL`=Project URL, `VITE_SUPABASE_PUBLISHABLE_KEY`=publishable key. 화면 코드에 빌드할 때 들어가는 값이라 런타임 변수가 아니라 **빌드 변수**에 넣는다
4. Deploy. 1~2분 뒤 주소가 나온다.
5. 배포 뒤 Settings > Build에서 Build watch paths의 Include를 `web/**`로 둔다(화면 코드가 바뀔 때만 빌드). `web/*`로 두면 `web/src` 안쪽 변경에 빌드가 돌지 않았다(2026.10.13).
6. 배포된 주소를 Supabase의 Site URL과 Redirect URLs에 넣는다(1의 3).

빌드 변수를 나중에 바꾸면 Deployments에서 다시 배포해야 반영된다.

화면 코드에는 공고 데이터가 들어가지 않는다. 공고는 로그인한 뒤 Supabase 비공개 저장소에서 받는다.

## 3. GitHub Secrets (매일 수집)

레포 Settings > Secrets and variables > Actions에 넣는다.

| 이름 | 값 |
| --- | --- |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SECRET_KEY` | secret key |
| `GEMINI_API_KEY` | aistudio.google.com > Get API key. 직무 유형 분류에 쓴다. 없으면 분류만 건너뛴다 |
| `KAKAO_REST_KEY` | 카카오 앱 REST API 키(아래 4). 없으면 아침 카톡만 건너뛴다 |
| `KAKAO_CLIENT_SECRET` | 카카오 앱 REST API 키의 클라이언트 시크릿 |

넣은 뒤 Actions > collect > Run workflow로 한 번 돌려 "Supabase 저장소에 올림" 줄이 나오는지 본다(2026.10.13 확인. 새 secret 키는 `apikey` 헤더만으로 올라간다). 키가 없으면 화면용 파일은 만들기만 하고 올리지 않는다.

## 4. 카카오 (아침 카톡)

매일 수집·매칭이 끝나면 카톡 "나와의 채팅"으로 새 공고 요약이 온다(카카오 "나에게 보내기", 무료). 처음 한 번만 연결한다. 메뉴 이름은 2026.10 developers.kakao.com 문서 기준이다.

1. developers.kakao.com에 카카오 계정으로 로그인하고 **앱 만들기**(이름 예: `careermap`).
2. 앱 설정
   - [앱] > [플랫폼 키] > [REST API 키]: REST API 키와 클라이언트 시크릿 값을 확인한다(시크릿은 처음부터 켜져 있다). 같은 곳의 **리다이렉트 URI**에 `https://careermap-web.oroloov.workers.dev/kakao.html`을 넣는다(`config/notify.yaml`의 대시보드 주소 + `redirect_path`).
   - [앱] > [제품 링크 관리] > [웹 도메인]: `https://careermap-web.oroloov.workers.dev`. 여기 없는 주소는 카톡 메시지에서 열리지 않는다.
   - [카카오 로그인] > [사용 설정]: 상태 ON.
   - [카카오 로그인] > [동의항목] > [접근권한]: **카카오톡 메시지 전송**(`talk_message`)을 선택 동의로 설정.
3. GitHub Secrets에 넣는다(위 3의 표): `KAKAO_REST_KEY`, `KAKAO_CLIENT_SECRET`.
4. Supabase SQL Editor에서 `supabase/migrations/005_kakao.sql`을 실행한다(토큰을 서버만 읽는 표).
5. 휴대폰이나 PC 브라우저에서 아래 주소를 연다. `<REST API 키>`만 바꾼다.

   ```
   https://kauth.kakao.com/oauth/authorize?response_type=code&scope=talk_message&client_id=<REST API 키>&redirect_uri=https://careermap-web.oroloov.workers.dev/kakao.html
   ```

   카카오 로그인과 동의를 마치면 "카톡 연결" 화면에 인가 코드가 나온다. 코드는 한 번만, 받은 직후에만 쓸 수 있다.
6. 바로 GitHub > Actions > **kakao** > Run workflow의 `code` 칸에 붙여 넣고 실행한다. 1~2분 뒤 오늘의 아침 카톡이 오면 끝이다.

- 그 뒤로는 매일 collect 마지막 단계(아침 카톡)가 보낸다. 같은 날 두 번 보내지 않는다. 오늘 것을 다시 받고 싶으면 kakao를 code 없이 실행한다(오늘 아직 못 받은 사람에게만 간다).
- 연결 토큰은 60일짜리인데, 카카오가 1개월 미만 남았을 때 새 토큰을 주면 매일 작업이 바꿔 저장한다. 그래서 매일 돌기만 하면 다시 연결할 일이 없다. 끊기면(보내기 단계가 실패하고 GitHub가 메일로 알림) 5~6을 다시 한다.
- 카톡에서 링크를 누르면 휴대폰 기본 브라우저로 다시 열린다. 카톡 안 브라우저에서는 구글 로그인이 막혀서다. 기본 브라우저에서 한 번 로그인해 두면 계속 쓴다.

## 개발할 때

```
uv run jobpost screen --data-dir <data 폴더> --out .dev-data/screen.json.gz
cd web && npm install && npm run dev
```

`web/.env`에 Supabase 값이 없으면 로그인 없이 `.dev-data/screen.json.gz`를 읽는다(개발 서버에서만). 검사는 `npm test`, `npm run lint`, `npm run build`.
