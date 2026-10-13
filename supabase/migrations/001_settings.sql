-- 사람별 설정(지금은 개인 필터). 본인 행만 읽고 쓴다(행 단위 권한).
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.settings (
  user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  filters jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.settings enable row level security;

grant select, insert, update on public.settings to authenticated;

drop policy if exists "본인 설정 읽기" on public.settings;
create policy "본인 설정 읽기" on public.settings
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 설정 만들기" on public.settings;
create policy "본인 설정 만들기" on public.settings
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "본인 설정 고치기" on public.settings;
create policy "본인 설정 고치기" on public.settings
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
