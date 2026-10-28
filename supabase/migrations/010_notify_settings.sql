-- 아침 알림 받기(관리 > 아침 알림). 사람마다 settings.notify에 켜기·끄기(enabled)를 둔다. 비어 있으면 받는다.
-- 매일 작업(서버 키)이 읽는다(src/jobpost/notify.py enabled).
-- 관리 화면이 알림 연결 상태(연결했는지, 마지막으로 보낸 날)를 보도록 telegram_links의 본인 줄을 읽게 한다.
-- 대화방 id(chat_id)는 화면에 필요 없어서 그 칸은 읽지 못한다.
-- Supabase SQL Editor에서 한 번 실행한다. 다시 실행해도 괜찮다.

alter table public.settings add column if not exists notify jsonb not null default '{}'::jsonb;

grant select (user_id, last_sent_on, updated_at) on public.telegram_links to authenticated;

drop policy if exists "본인 알림 연결 보기" on public.telegram_links;
create policy "본인 알림 연결 보기" on public.telegram_links
  for select to authenticated using (user_id = auth.uid());
