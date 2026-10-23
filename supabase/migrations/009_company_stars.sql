-- 관심 회사(★): 회사 화면에서 ★를 누른 회사. 심층분석(AI 웹 조사 모듈)을 만들 회사를 고르는 데도 쓴다.
-- 본인 줄만 읽고 쓴다. 매일 작업(심층분석)은 서버 키로 모두 읽는다.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.company_stars (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  company_key text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, company_key)
);

alter table public.company_stars enable row level security;

grant select, insert, delete on public.company_stars to authenticated;

drop policy if exists "본인 관심 회사 읽기" on public.company_stars;
create policy "본인 관심 회사 읽기" on public.company_stars
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 관심 회사 넣기" on public.company_stars;
create policy "본인 관심 회사 넣기" on public.company_stars
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "본인 관심 회사 빼기" on public.company_stars;
create policy "본인 관심 회사 빼기" on public.company_stars
  for delete to authenticated using (user_id = auth.uid());
