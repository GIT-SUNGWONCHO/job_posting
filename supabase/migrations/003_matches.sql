-- 사람별 매칭 결과. 매일 수집 뒤 서버 키로 다시 쓰고, 화면은 본인 행만 읽는다.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.matches (
  user_id uuid not null references auth.users (id) on delete cascade,
  posting_id text not null,
  score integer not null,
  parts jsonb not null,
  matched text[] not null default '{}',
  missing text[] not null default '{}',
  reason text,
  reason_meta jsonb,
  score_v integer not null,
  profile_v integer not null,
  computed_on date not null,
  primary key (user_id, posting_id)
);

alter table public.matches enable row level security;

grant select on public.matches to authenticated;
grant select, insert, update, delete on public.matches to service_role;
grant select on public.profiles, public.settings to service_role;

drop policy if exists "본인 매칭 읽기" on public.matches;
create policy "본인 매칭 읽기" on public.matches
  for select to authenticated using (user_id = auth.uid());
