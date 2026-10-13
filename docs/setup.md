# 운영 설정

계정을 만들고 키를 넣는 순서. 키 값은 이 문서에도, 코드와 커밋에도 적지 않는다. 넣을 곳은 GitHub Secrets와 Cloudflare Pages 환경 변수뿐이다.

## 1. Supabase (저장소, 로그인)

1. supabase.com에서 새 프로젝트를 만든다. 지역은 Northeast Asia (Seoul), 무료 등급.
2. **Storage**에서 저장소(bucket)를 만든다. 이름 `screen`, Public은 끈다(비공개).
3. **SQL Editor**에서 아래를 실행한다. 로그인한 사람만 화면용 파일을 읽을 수 있게 한다.

   ```sql
   create policy "로그인한 사람은 화면용 파일을 읽는다"
   on storage.objects for select to authenticated
   using (bucket_id = 'screen');
   ```

4. **Authentication**
   - 이메일 로그인을 켜 두고, 새 사용자 가입(Allow new users to sign up)은 끈다. 허용한 사람만 들어온다.
   - Users에서 본인 이메일을 초대한다(지인도 여기서 초대).
   - URL Configuration의 Site URL에 대시보드 주소(Cloudflare Pages, 아래 2번)를, Redirect URLs에 같은 주소와 `http://localhost:5173`을 넣는다.
5. **Project Settings > API Keys**에서 두 값을 확인한다.
   - Project URL과 publishable key(`sb_publishable_…`): 화면에서 쓴다. 공개돼도 되는 키다.
   - secret key(`sb_secret_…`): 매일 수집 작업만 쓴다. 절대 화면이나 채팅에 붙이지 않는다.

## 2. Cloudflare Pages (화면)

1. Workers & Pages > Create > Pages > Connect to Git에서 이 레포를 고른다.
2. 빌드 설정
   - Root directory: `web`
   - Build command: `npm run build`
   - Build output directory: `dist`
   - 환경 변수: `NODE_VERSION`=`22`, `VITE_SUPABASE_URL`=Project URL, `VITE_SUPABASE_ANON_KEY`=publishable key
3. 배포된 주소(`*.pages.dev`)를 Supabase의 Site URL과 Redirect URLs에 넣는다(1-4).

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
