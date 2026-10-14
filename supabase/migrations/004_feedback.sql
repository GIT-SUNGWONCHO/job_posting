-- 매칭 결과에 남기는 내 평가(○ 지원할 만함 / △ 애매 / × 아님)와 코멘트. 매칭 기준을 만드는 정답으로 쓴다.
-- 평가한 순간의 점수·판단 근거·모델·지침 버전을 snapshot에 함께 저장한다(다시 매겨도 그때 무엇을 보고 평가했는지 남게).
-- 같은 매칭 결과(match_key: 지침 버전·프로필 버전·모델)에는 한 줄만 두고 고치면 덮어쓴다. 회차가 바뀌면 새 줄.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.feedback (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  posting_id text not null,
  match_key text not null,
  label text not null check (label in ('good', 'maybe', 'bad')),
  comment text,
  snapshot jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, posting_id, match_key)
);

alter table public.feedback enable row level security;

grant select, insert, update, delete on public.feedback to authenticated;
grant select on public.feedback to service_role;

drop policy if exists "본인 평가 읽기" on public.feedback;
create policy "본인 평가 읽기" on public.feedback
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 평가 만들기" on public.feedback;
create policy "본인 평가 만들기" on public.feedback
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "본인 평가 고치기" on public.feedback;
create policy "본인 평가 고치기" on public.feedback
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "본인 평가 지우기" on public.feedback;
create policy "본인 평가 지우기" on public.feedback
  for delete to authenticated using (user_id = auth.uid());
