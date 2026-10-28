-- 내 리서치 노트: 사람마다의 회사 노트(정해진 블록 JSON, 형식은 docs/content-rules.md "내 리서치 노트").
-- 앱은 본인 줄만 읽는다. 노트는 지금 매일 작업(jobpost notes)이 서버 키로 넣는다(data 브랜치 notes/).
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.research_notes (
  user_id uuid not null references auth.users (id) on delete cascade,
  company_key text not null,
  note jsonb not null,
  updated_on date not null,
  saved_at timestamptz not null default now(),
  primary key (user_id, company_key)
);

alter table public.research_notes enable row level security;

grant select, delete on public.research_notes to authenticated;
grant select, insert, update, delete on public.research_notes to service_role;

drop policy if exists "본인 노트 읽기" on public.research_notes;
create policy "본인 노트 읽기" on public.research_notes
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "본인 노트 지우기" on public.research_notes;
create policy "본인 노트 지우기" on public.research_notes
  for delete to authenticated using (user_id = auth.uid());
