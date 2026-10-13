-- 사람별 프로필(경력·프로젝트·스킬). 본인 행만 읽고 쓴다(행 단위 권한).
-- 매일 매칭 작업은 서버 키로 읽는다. 이력서 원문은 저장하지 않는다.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.profiles (
  user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  version integer not null default 1,
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

grant select, insert, update on public.profiles to authenticated;

drop policy if exists "본인 프로필 읽기" on public.profiles;
create policy "본인 프로필 읽기" on public.profiles
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 프로필 만들기" on public.profiles;
create policy "본인 프로필 만들기" on public.profiles
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "본인 프로필 고치기" on public.profiles;
create policy "본인 프로필 고치기" on public.profiles
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
