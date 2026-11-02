-- 매칭 메모: 평가 코멘트에서 AI가 뽑은 지원자에 대한 메모(경험·역량의 한계와 강점). 사람마다 한 줄.
-- 매일 매칭이 지원자 요약 끝에 붙여 쓴다. 지금은 화면에 보이지 않고, 서버 키(jobpost memo)만 쓴다.
-- memo: {"lines": [...], "comments": 코멘트 수, "model": 모델, "on": 날짜}. 메모가 바뀌면 version을 올린다.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

create table if not exists public.match_memos (
  user_id uuid primary key references auth.users (id) on delete cascade,
  memo jsonb not null default '{}'::jsonb,
  version integer not null default 1,
  updated_at timestamptz not null default now()
);

alter table public.match_memos enable row level security;

-- 본인 메모는 읽을 수만 있다(화면에 보일지는 나중에 정한다). 쓰기는 서버 키만
grant select on public.match_memos to authenticated;
grant select, insert, update, delete on public.match_memos to service_role;

drop policy if exists "본인 메모 읽기" on public.match_memos;
create policy "본인 메모 읽기" on public.match_memos
  for select to authenticated using (user_id = auth.uid());
