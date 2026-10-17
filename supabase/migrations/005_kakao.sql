-- 아침 카톡("나에게 보내기") 연결. 사람마다 1줄.
-- 리프레시 토큰은 매일 작업(서버 키)만 읽고 쓴다. 화면(로그인한 사람)과 공개 키에는 아무 권한도 주지 않는다.
-- 카카오가 1개월 미만 남았을 때 새 토큰을 주면 매일 작업이 바꿔 저장한다(src/jobpost/notify.py).
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.kakao_links (
  user_id uuid primary key references auth.users (id) on delete cascade,
  refresh_token text not null,
  refresh_expires_at timestamptz,
  last_sent_on date,
  updated_at timestamptz not null default now()
);

alter table public.kakao_links enable row level security;

revoke all on public.kakao_links from anon, authenticated;
grant select, insert, update, delete on public.kakao_links to service_role;
