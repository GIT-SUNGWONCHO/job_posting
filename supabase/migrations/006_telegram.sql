-- 아침 알림을 받는 텔레그램 대화방. 사람마다 1줄. 매일 작업(서버 키)만 읽고 쓴다.
-- 대화방 id만으로는 메시지를 보낼 수 없지만(봇 토큰이 있어야 함) 화면에는 필요 없어서 권한을 주지 않는다.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.telegram_links (
  user_id uuid primary key references auth.users (id) on delete cascade,
  chat_id bigint not null,
  last_sent_on date,
  updated_at timestamptz not null default now()
);

alter table public.telegram_links enable row level security;

revoke all on public.telegram_links from anon, authenticated;
grant select, insert, update, delete on public.telegram_links to service_role;
