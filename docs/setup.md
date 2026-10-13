# 운영 설정

계정을 만들고 키를 넣는 순서. 키 값은 이 문서에도, 코드와 커밋에도 적지 않는다. 넣을 곳은 GitHub Secrets와 Cloudflare 빌드 변수뿐이다.

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

3. **Authentication**
   - 이메일 로그인을 켜 두고, 새 사용자 가입(Allow new users to sign up)은 **반드시** 끈다. publishable 키는 공개되는 값이라, 가입이 열려 있으면 누구나 가입해서 "로그인한 사람"이 될 수 있다.
   - Users에서 본인 이메일을 초대한다(지인도 여기서 초대).
   - URL Configuration의 Site URL에 대시보드 주소(Cloudflare, 아래 2)를, Redirect URLs에 같은 주소와 `http://localhost:5173`을 넣는다.
4. **Project Settings > API Keys**에서 두 값을 확인한다.
   - Project URL과 publishable key(`sb_publishable_…`): 화면에서 쓴다. 공개돼도 되는 키다.
   - secret key(`sb_secret_…`): 매일 수집 작업만 쓴다. 절대 화면이나 채팅에 붙이지 않는다.

## 2. Cloudflare Workers (화면)

Vercel과 같은 역할이다. GitHub 레포를 연결해 두면 main에 올릴 때마다 Cloudflare가 가져가 빌드하고 배포한다. 처음에는 Cloudflare Access(로그인 문)도 쓰려고 골랐는데, 로그인을 Supabase로 바꾼 뒤로는 화면 코드 호스팅만 한다. 2026.10 대시보드에는 Pages 대신 Workers 만들기("Create application")만 보여서 Workers 정적 사이트로 올린다. 설정은 `web/wrangler.jsonc`에 있다.

1. dash.cloudflare.com > Workers & Pages > Create application > GitHub 레포 가져오기.
   - GitHub 연결 창에서 "Only select repositories"로 이 레포만 허용한다.
2. 이름: `careermap`(`web/wrangler.jsonc`의 name과 같아야 한다). 주소는 `careermap.<계정>.workers.dev`가 된다.
3. 빌드 설정
   - Build command: `npm run build`
   - Deploy command: `npx wrangler deploy`(기본값 그대로)
   - Enable Preview builds: 끔. 매일 커밋되는 `data` 브랜치 때문에 쓸데없는 빌드가 돌지 않게 한다
   - Protect with Cloudflare Access: 끔(로그인은 Supabase)
   - Advanced settings > Path(root directory): `web`
   - Advanced settings > Build variables: `NODE_VERSION`=`22`, `VITE_SUPABASE_URL`=Project URL, `VITE_SUPABASE_PUBLISHABLE_KEY`=publishable key. 화면 코드에 빌드할 때 들어가는 값이라 런타임 변수가 아니라 **빌드 변수**에 넣는다
4. Deploy. 1~2분 뒤 주소가 나온다.
5. 배포 뒤 Settings > Build에서 Build watch paths의 Include를 `web/*`로 둔다(화면 코드가 바뀔 때만 빌드).
6. 배포된 주소를 Supabase의 Site URL과 Redirect URLs에 넣는다(1의 3).

빌드 변수를 나중에 바꾸면 Deployments에서 다시 배포해야 반영된다.

화면 코드에는 공고 데이터가 들어가지 않는다. 공고는 로그인한 뒤 Supabase 비공개 저장소에서 받는다.

## 3. GitHub Secrets (매일 수집)

레포 Settings > Secrets and variables > Actions에 넣는다.

| 이름 | 값 |
| --- | --- |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SECRET_KEY` | secret key |

넣은 뒤 Actions > collect > Run workflow로 한 번 돌려 "Supabase 저장소에 올림" 줄이 나오는지 본다. 키가 없으면 화면용 파일은 만들기만 하고 올리지 않는다.

## 개발할 때

```
uv run jobpost screen --data-dir <data 폴더> --out .dev-data/screen.json.gz
cd web && npm install && npm run dev
```

`web/.env`에 Supabase 값이 없으면 로그인 없이 `.dev-data/screen.json.gz`를 읽는다(개발 서버에서만). 검사는 `npm test`, `npm run lint`, `npm run build`.
