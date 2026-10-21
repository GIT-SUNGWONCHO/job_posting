-- 지원 상태: 공고마다 고른 지원 단계(관심 → 지원 → 서류 합격 → 면접 → 결과, 따로 관심 없음)와 메모·날짜.
-- 공고가 마감돼 화면용 파일에서 빠져도 지원 현황에 보이게 회사·제목·주소·마감을 snapshot에 함께 둔다.
-- 본인 줄만 읽고 쓴다. 매일 작업(서버 키)은 읽기만 한다(아침 알림: 관심 공고 마감 임박, 지원·관심 없음 공고는 빼기).
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.applications (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  posting_id text not null,
  stage text not null check (stage in ('interest', 'applied', 'passed', 'interview', 'result', 'dismissed')),
  outcome text check (outcome in ('pass', 'fail')),
  memo text,
  next_on date,
  next_label text,
  dates jsonb not null default '{}'::jsonb,
  snapshot jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, posting_id)
);

alter table public.applications enable row level security;

grant select, insert, update, delete on public.applications to authenticated;
grant select on public.applications to service_role;

drop policy if exists "본인 지원 상태 읽기" on public.applications;
create policy "본인 지원 상태 읽기" on public.applications
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 지원 상태 만들기" on public.applications;
create policy "본인 지원 상태 만들기" on public.applications
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "본인 지원 상태 고치기" on public.applications;
create policy "본인 지원 상태 고치기" on public.applications
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "본인 지원 상태 지우기" on public.applications;
create policy "본인 지원 상태 지우기" on public.applications
  for delete to authenticated using (user_id = auth.uid());
