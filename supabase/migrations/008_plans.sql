-- 할 일(커리어 탭 성장 계획): 달마다 적는 학습·프로젝트·자격증 할 일. "채우면 좋은 것"에서 스킬을 골라 넣기도 한다.
-- 본인 줄만 읽고 쓴다. 매일 작업은 아직 읽지 않는다(월간 커리어 리포트를 만들 때 서버 키 읽기를 더한다).
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  month text not null check (month ~ '^\d{4}-\d{2}$'),
  text text not null,
  kind text not null default 'study' check (kind in ('study', 'project', 'cert', 'etc')),
  skill text,
  done boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists plans_user_month on public.plans (user_id, month);

alter table public.plans enable row level security;

grant select, insert, update, delete on public.plans to authenticated;

drop policy if exists "본인 할 일 읽기" on public.plans;
create policy "본인 할 일 읽기" on public.plans
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 할 일 만들기" on public.plans;
create policy "본인 할 일 만들기" on public.plans
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "본인 할 일 고치기" on public.plans;
create policy "본인 할 일 고치기" on public.plans
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "본인 할 일 지우기" on public.plans;
create policy "본인 할 일 지우기" on public.plans
  for delete to authenticated using (user_id = auth.uid());
