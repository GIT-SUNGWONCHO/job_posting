"""명령줄 실행: uv run jobpost collect --data-dir data, uv run jobpost screen --data-dir data --out screen.json.gz"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from . import (
    ai,
    bodyread,
    config,
    dart,
    db,
    facts,
    feedback,
    jobtypes,
    notes,
    notify,
    official,
    pipeline,
    publish,
    recommend,
    screen,
)
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobpost")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="공고를 수집해 data 폴더에 쌓는다")
    c.add_argument("--data-dir", type=Path, default=Path("data"))
    c.add_argument("--sources", help="쉼표로 구분(zighang,remember,saramin,wanted,jobkorea). 생략하면 켜 둔 수집처 전부")
    c.add_argument("--max-pages", type=int, help="시험용: 조회마다 최대 페이지 수")
    c.add_argument("--detail-budget", type=int, help="직행 상세를 받을 최대 건수")

    k = sub.add_parser("check-source", help="수집처가 이 환경(GitHub Actions 등)에서 열리는지 시험한다. 아무것도 저장하지 않는다")
    k.add_argument("--sources", required=True, help="쉼표로 구분(예: jobkorea,wanted)")
    k.add_argument("--details", type=int, default=2, help="본문(상세)도 이만큼 받아 본다")

    s = sub.add_parser("screen", help="화면용 파일(오늘 열린 국내 공고 + 회사)을 만든다")
    s.add_argument("--data-dir", type=Path, default=Path("data"))
    s.add_argument("--out", type=Path, default=Path("screen.json.gz"))
    s.add_argument("--upload", action="store_true",
                   help="Supabase 저장소에 올린다(환경 변수 SUPABASE_URL, SUPABASE_SECRET_KEY가 있을 때)")

    m = sub.add_parser("match", help="사람마다 매칭 점수와 매칭 이유를 Supabase에 쓴다")
    m.add_argument("--data-dir", type=Path, default=Path("data"))
    m.add_argument("--sample", action="store_true", help="기준 샘플(config/match_sample.yaml)만 다시 매긴다")
    m.add_argument("--model", help="이번 실행만 다른 모델로(회차 시험)")
    m.add_argument("--max-calls", type=int, help="이번 실행 최대 AI 호출 수(비우면 config/ai.yaml match.max_calls). 따라잡기용")
    m.add_argument("--max-minutes", type=float, help="이번 실행 최대 시간(분)")

    jc = sub.add_parser("jobtypes-check", help="시험: 보조 직무 유형을 골라 보고 지금 분류와 비교한다(저장 없음)")
    jc.add_argument("--data-dir", type=Path, default=Path("data"))
    jc.add_argument("--n", type=int, default=160)
    br = sub.add_parser("bodyread", help="본문 읽기: 원문이 이미지뿐인 후보 공고의 이미지 글자를 AI로 읽어 ocr.jsonl에 쌓는다")
    br.add_argument("--data-dir", type=Path, default=Path("data"))
    f = sub.add_parser("facts", help="후보 공고의 매칭 항목을 AI로 정리해 data 폴더 facts.jsonl에 쌓는다")
    f.add_argument("--data-dir", type=Path, default=Path("data"))
    f.add_argument("--max-calls", type=int, help="이번 실행 최대 호출 수(비우면 config/ai.yaml facts.max_calls). 따라잡기용")
    f.add_argument("--max-minutes", type=float, help="이번 실행 최대 시간(분)")
    f.add_argument("--parallel", action="store_true", help="따라잡기: 키마다 하나씩 함께 돌린다")
    f.add_argument("--only", help="시험: 이 공고 id들(쉼표)만 정리해 --out 파일에 쓴다(facts.jsonl은 그대로)")
    f.add_argument("--out", default="trials/facts_trial.jsonl", help="--only일 때 쓸 파일(data 폴더 안)")

    r = sub.add_parser("feedback", help="회차 리포트: 로그에는 건수·지표만, --out에는 공고별 평가·판단 근거·바꿀 후보(비공개)")
    r.add_argument("--data-dir", type=Path, default=Path("data"))
    r.add_argument("--out", type=Path, help="비공개 리포트를 쓸 파일(워크플로가 암호화한다. 로그에 찍지 않는다)")

    mm = sub.add_parser("memo", help="매칭 메모: 평가 코멘트에서 지원자에 대한 메모를 AI로 뽑아 match_memos 표에 쓴다")
    mm.add_argument("--data-dir", type=Path, default=Path("data"))

    n = sub.add_parser("notify", help="아침 알림: 연결한 사람마다 새 공고 요약을 보낸다(채널은 config/notify.yaml)")
    n.add_argument("--data-dir", type=Path, default=Path("data"))
    n.add_argument("--telegram-connect", action="store_true",
                   help="텔레그램 연결: 봇에게 최근에 /start를 보낸 대화방을 저장한 뒤 바로 보낸다")
    n.add_argument("--kakao-code", metavar="CODE", help="카톡 연결: 인가 코드로 토큰을 받아 저장한 뒤 바로 보낸다")
    n.add_argument("--user-id", help="연결할 사람(프로필이 여럿일 때)")
    n.add_argument("--again", action="store_true", help="오늘 이미 보냈어도 다시 보낸다(모양 확인용)")

    t = sub.add_parser("research-test", help="심층분석 시험: 구글 검색 근거로 회사 사실을 받아 보고 근거 수·출처를 로그로 낸다")
    t.add_argument("--company", required=True)
    t.add_argument("--models", default="", help="쉼표로 여러 모델(비우면 config/ai.yaml)")
    nt = sub.add_parser("notes", help="내 리서치 노트: data 폴더 notes/*.json을 사람마다 Supabase에 넣는다")
    nt.add_argument("--data-dir", type=Path, default=Path("data"))
    d = sub.add_parser("dart", help="회사 기본정보: 공고 회사를 DART와 잇고 기업개황·재무·직원·공시를 data/dart/에 쌓는다")
    d.add_argument("--data-dir", type=Path, default=Path("data"))
    d.add_argument("--budget", type=int, help="이번 실행에서 쓸 최대 요청 수(비우면 config/dart.yaml)")
    d.add_argument("--raw", type=int, default=0, help="처음 이만큼의 DART 응답을 로그에 남긴다(해석 확인용)")
    d.add_argument("--minutes", type=float, help="이 시간(분)이 지나면 멈춘다(비우면 config/dart.yaml max_minutes)")
    d.add_argument("--find", help="쉼표로 구분한 말: DART 회사 목록에서 이 말이 들어간 이름을 로그에 남긴다(손으로 이을 때)")
    of = sub.add_parser("official", help="공식 목록(공정위 기업집단 소속회사·알리오 공공기관·국민연금 사업장)을 data/official/에 받는다")
    of.add_argument("--data-dir", type=Path, default=Path("data"))
    of.add_argument("--what", default="groups,public,nps", help="쉼표로 구분: groups, public, nps")
    sc = sub.add_parser("settings-clear", help="조건 필터의 한 항목을 비운다(= 전부 통과). 사용자가 한 명일 때만(지인이 생기면 화면에서)")
    sc.add_argument("--key", required=True, choices=["company_types", "regions", "employment_types", "career", "job_types"])
    sc.add_argument("--add", help="비우지 않고 이 값을 목록에 더한다(쉼표로 여러 개. 예: job_types에 analytics_eng)")
    mi = sub.add_parser("migrate-industries", help="프로필의 업종을 지난 id에서 코드로 옮긴다(백업 먼저). 로그에는 건수만")
    mi.add_argument("--apply", action="store_true", help="실제로 바꾼다(없으면 건수만 센다)")
    mc = sub.add_parser("monthly-check", help="월간 점검: 업종 분포·KSIC·업종 사전 밖 문장·예외 비교(고치지 않음)")
    mc.add_argument("--data-dir", type=Path, default=Path("data"))
    ms = sub.add_parser("match-stats", help="시험: 규칙 점수 구간별 AI 판정·내 평가·공고 수(로그에는 건수만)")
    ms.add_argument("--data-dir", type=Path, default=Path("data"))
    ps = sub.add_parser("prescreen-trial", help="시험: 사전 거르기(조건·규칙 v2·규칙 v3·AI 묶음)가 줄이는 양과 잃는 정답 수(로그에는 건수만)")
    ps.add_argument("--data-dir", type=Path, default=Path("data"))
    ps.add_argument("--ai-sample", type=int, default=300, help="AI 묶음 거르기를 시험할 공고 수(30건에 1번 호출)")
    mc = sub.add_parser("method-compare", help="시험: 매칭 방식 A(지금)·B(항목 풀)·C(고정 틀)·D(AI 점수)·E(임베딩)를 내 평가로 견준다(로그에는 지표만)")
    mc.add_argument("--data-dir", type=Path, default=Path("data"))
    mc.add_argument("--mode", choices=["score", "evaluate"], default="evaluate",
                    help="score: 기준 샘플 전부를 미리 매겨 비공개 저장소에 둔다(AI 부름), evaluate: 저장한 점수와 평가로 지표만(AI 없음)")
    mc.add_argument("--methods", default="BCDE", help="score에서 새로 매길 방식(A는 지금 매칭 결과를 씀)")
    mc.add_argument("--rounds", type=int, default=2, help="score에서 방식마다 몇 번 매길지(흔들림을 보려고 2)")
    da = sub.add_parser("dart-audit", help="시험: DART 고유번호마다 최근 감사보고서에서 실적을 읽어 본다(저장 없음)")
    da.add_argument("--codes", required=True, help="쉼표로 구분한 DART 고유번호")
    da.add_argument("--raw", type=int, default=3, help="못 읽은 회사 이만큼은 손익계산서 앞부분을 남긴다")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.cmd == "collect":
        sources = args.sources.split(",") if args.sources else None
        summary = pipeline.run(args.data_dir, sources=sources, max_pages=args.max_pages,
                               detail_budget=args.detail_budget)
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=1)
        print()
        failed = [n for n, s in summary["sources"].items() if s["error_count"] and not s["fetched"]]
        return 1 if failed and len(failed) == len(summary["sources"]) else 0
    if args.cmd == "check-source":
        out = {name: pipeline.check_source(name, details=args.details) for name in args.sources.split(",")}
        json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0 if all(v["ok"] for v in out.values()) else 1
    if args.cmd == "screen":
        built, bodies = screen.build(args.data_dir, with_career=True)
        path = screen.write(built, args.out)
        body_paths = screen.write_bodies(bodies, args.out.parent)
        # 회사 기본정보 파일은 실패해도 화면용 파일은 올린다(data/dart/가 깨진 날에도 공고·매칭·알림은 계속)
        companies_path = None
        try:
            companies_path = screen.write(screen.build_companies(args.data_dir, built), args.out.parent / "companies.json.gz")
        except (OSError, ValueError) as e:
            logging.warning("회사 기본정보 파일을 만들지 못함: %s", e)
        logging.info("화면용 파일: 공고 %d건, 회사 %d곳, %s KB / 본문 %d건, %d개 파일 %s KB / 회사 기본정보 %s KB",
                     built["counts"]["open"], built["counts"]["companies"], path.stat().st_size // 1024,
                     len(bodies["bodies"]), len(body_paths), sum(p.stat().st_size for p in body_paths) // 1024,
                     companies_path.stat().st_size // 1024 if companies_path else "-")
        if args.upload:
            if not publish.configured():
                logging.info("Supabase 설정이 없어 올리지 않음")
            else:
                publish.upload(path)
                for bp in body_paths:
                    publish.upload(bp, name=f"bodies/{bp.name}")
                if companies_path:
                    publish.upload(companies_path, name="companies.json.gz")
                logging.info("Supabase 저장소에 올림")
    if args.cmd == "notes":
        if not db.configured():
            logging.info("Supabase 설정이 없어 리서치 노트를 건너뜀")
            return 0
        store = db.DB()
        store.check_server_key()
        summary = notes.run(args.data_dir, store)
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
        return 0
    if args.cmd == "dart":
        if not dart.configured():
            logging.info("DART 키(DART_API_KEY)가 없어 회사 기본정보를 건너뜀")
            return 0
        summary = dart.run(args.data_dir, date.today(), budget=args.budget, raw=args.raw, minutes=args.minutes,
                           find=[w.strip() for w in (args.find or '').split(',') if w.strip()])
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=1)
        print()
        # 한도·실패로 멈춰도 받은 만큼은 저장했으니 다음 단계(화면용 파일)는 계속한다
        return 0
    if args.cmd == "official":
        import os
        summary = official.run(args.data_dir, args.what.split(","), os.environ.get("DATA_GO_KR_KEY"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if not any("error" in v for v in summary.values()) else 1
    if args.cmd == "settings-clear":
        client = db.DB()
        rows = client.select("settings", "select=user_id,filters")
        if len(rows) != 1:
            print(json.dumps({"skipped": f"설정이 {len(rows)}명분이라 하지 않음(한 명일 때만)"}, ensure_ascii=False))
            return 1
        filters = dict(rows[0].get("filters") or {})
        before = filters.get(args.key)
        if args.add:
            filters[args.key] = sorted(set(before or []) | {v.strip() for v in args.add.split(",") if v.strip()})
        else:
            filters[args.key] = [] if args.key != "career" else {}
        client.update("settings", f"user_id=eq.{rows[0]['user_id']}", {"filters": filters})
        print(json.dumps({"key": args.key, "before": before, "after": filters[args.key]}, ensure_ascii=False))
        return 0
    if args.cmd == "dart-audit":
        if not dart.configured():
            logging.info("DART 키(DART_API_KEY)가 없음")
            return 1
        rows = dart.audit_check([c.strip() for c in args.codes.split(",") if c.strip()], date.today(), raw=args.raw)
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    if args.cmd == "match":
        if not db.configured():
            logging.info("Supabase 설정이 없어 매칭을 건너뜀")
            return 0
        only = set(recommend.sample_ids()) if args.sample else None
        built, bodies = screen.build(args.data_dir, keep=only)
        store = db.DB()
        store.check_server_key()
        summary = recommend.run(built, bodies, store, recommend.make_client(args.model), date.today(),
                                facts.load(args.data_dir), only=only, max_calls=args.max_calls,
                                max_minutes=args.max_minutes)
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
    if args.cmd == "method-compare":
        import gzip
        import tempfile

        from . import methods
        store = db.DB()
        keep = {r["posting_id"] for r in store.select("feedback", "select=posting_id")} | set(recommend.sample_ids())
        built, bodies = screen.build(args.data_dir, keep=keep)
        if args.mode == "score":
            saved, lines = methods.score_sample(built, bodies, facts.load(args.data_dir), store, recommend.make_client(),
                                                date.today(), methods=args.methods, rounds=args.rounds)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "methods.json.gz"
                path.write_bytes(gzip.compress(json.dumps(saved, ensure_ascii=False).encode()))
                publish.upload(path, name=methods.SAVE_NAME)
            print("\n".join(lines + ["저장함(비공개 저장소)"]))
            return 0
        raw = publish.download(methods.SAVE_NAME)
        if raw is None:
            print("저장한 점수가 없다. 먼저 --mode score로 매긴다")
            return 1
        print("\n".join(methods.evaluate(built, store, json.loads(gzip.decompress(raw)))))
        return 0
    if args.cmd == "prescreen-trial":
        from . import prescreen
        store = db.DB()
        rated = {r["posting_id"] for r in store.select("feedback", "select=posting_id")}
        built, bodies = screen.build(args.data_dir, keep=rated)
        client = recommend.make_client() if args.ai_sample > 0 else None
        print("\n".join(prescreen.trial(built, bodies, facts.load(args.data_dir), store, client, date.today(),
                                        ai_sample=args.ai_sample)))
        return 0
    if args.cmd == "migrate-industries":
        from . import migrate
        print(json.dumps(migrate.industries(db.DB(), apply=args.apply), ensure_ascii=False))
        return 0
    if args.cmd == "monthly-check":
        from . import monthly
        print("\n".join(monthly.report(args.data_dir)))
        return 0
    if args.cmd == "match-stats":
        built, bodies = screen.build(args.data_dir)
        print("\n".join(recommend.stats(built, bodies, db.DB(), date.today())))
        return 0
    if args.cmd == "jobtypes-check":
        st = Store(args.data_dir)
        out = jobtypes.check_secondary(st.state, st.load_postings(), st.load_details(), ai.Gemini(), n=args.n)
        json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    if args.cmd == "bodyread":
        built, _ = screen.build(args.data_dir)
        settings_b: list[dict] = []
        if db.configured():
            store_b = db.DB()
            store_b.check_server_key()
            settings_b = store_b.select("settings", "select=user_id,filters")
        wanted = facts.candidates_for_all(built, settings_b)
        details = Store(args.data_dir).load_details()
        client = ai.Gemini() if ai.configured() else None
        summary = bodyread.run(args.data_dir, wanted, details, client, date.today().isoformat())
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
        return 0
    if args.cmd == "facts":
        built, bodies = screen.build(args.data_dir)
        settings: list[dict] = []
        if db.configured():
            store = db.DB()
            store.check_server_key()
            settings = store.select("settings", "select=user_id,filters")
        wanted = facts.candidates_for_all(built, settings)
        client = ai.Gemini() if ai.configured() else None
        # --parallel: 키마다 클라이언트 하나씩 함께 돌린다(키마다 다른 구글 클라우드 프로젝트라 한도가 따로)
        clients = ([ai.Gemini(key_index=i) for i in range(len(ai.api_keys()))]
                   if client is not None and args.parallel else None)
        trial = [x.strip() for x in (args.only or "").split(",") if x.strip()]
        summary = facts.run(args.data_dir, built, bodies, trial or wanted, client, date.today().isoformat(),
                            max_calls=args.max_calls or (len(trial) if trial else None), max_minutes=args.max_minutes,
                            file=args.out if trial else facts.FILE, clients=clients)
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
    if args.cmd == "notify":
        if not db.configured() or not (notify.channels() or args.telegram_connect or args.kakao_code):
            logging.info("Supabase나 알림 채널 키가 없어 아침 알림을 건너뜀")
            return 0
        store = db.DB()
        store.check_server_key()
        try:
            if args.telegram_connect:
                logging.info("텔레그램 연결: 사람 %s", notify.connect_telegram(store, args.user_id)[:8])
            if args.kakao_code:
                logging.info("카톡 연결: 사람 %s", notify.connect_kakao(store, args.kakao_code, args.user_id)[:8])
        except ValueError as e:  # 사람이 고칠 수 있는 연결 문제는 한 줄로
            logging.error("연결 안 됨: %s", e)
            return 1
        built, _ = screen.build(args.data_dir)
        summary = notify.run(built, store, date.today(), again=args.again)
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
        return 1 if summary.get("errors") else 0  # 실패하면 Actions가 메일로 알려 준다
    if args.cmd == "research-test":
        if not ai.configured():
            logging.info("GEMINI_API_KEY가 없어 건너뜀")
            return 0
        return _research_test(args.company, [m.strip() for m in args.models.split(",") if m.strip()] or [None])
    if args.cmd == "feedback":
        if not db.configured():
            logging.info("Supabase 설정이 없어 건너뜀")
            return 0
        store = db.DB()
        store.check_server_key()
        ids = recommend.sample_ids()
        quoted = ",".join(f'"{i}"' for i in ids)
        matches = store.select("matches", "select=user_id,posting_id,score,parts,missing,reason,reason_meta,score_v,profile_v"
                                          f"&posting_id=in.({quoted})")
        rows = store.select("feedback", "select=user_id,posting_id,match_key,label,comment,updated_at&order=updated_at")
        sample = config.load("match_sample")["postings"]
        print("\n".join(feedback.report(sample, matches, rows, private=False)))
        if args.out:
            built, _ = screen.build(args.data_dir)
            names = {k: c["name"] for k, c in built["companies"].items()}
            every: list[dict] = []
            while True:  # Supabase는 한 번에 1,000줄까지 준다
                page = store.select("matches", "select=user_id,posting_id,score,score_v,rule:parts->rule,kind:parts->>kind"
                                               f"&order=user_id,posting_id&limit=1000&offset={len(every)}")
                every += page
                if len(page) < 1000:
                    break
            memos = recommend.load_memos(store)
            memo_out = [f"MEMO\t{user[:8]}\t{line}" for user, ls in memos.items() for line in ls]
            defaults = config.load("filters")
            settings = {r["user_id"]: r.get("filters") or {} for r in store.select("settings", "select=user_id,filters")}
            funnels = [line for user in sorted(settings)
                       for line in feedback.funnel(built, user, {**defaults, **settings[user]})]
            lines = (feedback.report(sample, matches, rows) + feedback.sample_dump(sample, matches, rows)
                     + memo_out + funnels + feedback.ranking(built, every)
                     + feedback.candidates(sample, built["postings"], names, every))
            args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logging.info("비공개 리포트 %d줄을 파일에 씀", len(lines))
    if args.cmd == "memo":
        if not db.configured() or not ai.configured():
            logging.info("Supabase나 GEMINI_API_KEY가 없어 매칭 메모를 건너뜀")
            return 0
        store = db.DB()
        store.check_server_key()
        rows = store.select("feedback", "select=user_id,posting_id,label,comment,updated_at&order=updated_at")
        state = Store(args.data_dir).state
        titles = {uid: (r.get("company", ""), r.get("title", "")) for uid, r in state.items()}
        current = {r["user_id"]: r for r in store.select("match_memos", "select=user_id,memo,version")}
        client = ai.Gemini()
        changed = 0
        for user in sorted({r["user_id"] for r in rows}):
            old = current.get(user) or {}
            before = (old.get("memo") or {}).get("lines") or []
            comments = feedback.latest_comments(rows, user, titles)
            # 지금 메모를 합치게 하면 막연한 문장이 계속 남아서, 코멘트에서 처음부터 다시 뽑는다(코멘트가 전부 남아 있다)
            lines = feedback.memo_lines(comments, [], client)
            if lines != before:
                store.insert("match_memos", [{"user_id": user, "version": (old.get("version") or 0) + 1,
                                              "updated_at": datetime.now(UTC).isoformat(),
                                              "memo": {"lines": lines, "comments": len(comments), "model": client.model,
                                                       "on": date.today().isoformat()}}])
                changed += 1
        # 메모 내용은 로그에 남기지 않는다(공개 로그). 회차 리포트의 암호화한 부분에서 본다
        logging.info("매칭 메모: 사람 %d명 중 %d명 바뀜", len({r["user_id"] for r in rows}), changed)
    return 0


def _research_test(company: str, models: list[str | None]) -> int:
    """웹 조사 모듈을 만들기 전에 검색 근거가 되는지, 출처가 어떤 모양인지 본다(키는 로그에 남기지 않는다)."""
    import time

    import requests

    prompt = (f"회사: {company}\n"
              "공개된 웹 자료로 확인되는 사실만 한국어 문장 5개로 쓰세요. 주제: 이 회사의 데이터·AI 조직(팀 이름, 하는 일), "
              "최근 1년의 데이터·AI 관련 발표나 투자. 추측하지 말고, 확인되지 않으면 쓰지 마세요.")
    for model in models:
        client = ai.Gemini(model=model)
        started = time.monotonic()
        try:
            got = client.grounded(prompt)
        except ai.AIError as e:
            import re

            text = str(e)
            # 검색 근거가 무료 등급 밖인지, 그냥 오늘 한도를 다 쓴 건지 가린다: 같은 모델로 보통 호출도 해 본다
            try:
                plain = client.json("1 더하기 1은? 숫자만", {"type": "object", "properties": {"a": {"type": "string"}}})
            except ai.AIError as e2:
                plain = f"실패 {str(e2)[:120]}"
            print(json.dumps({"model": client.model, "error": text[:160],
                              "quota": sorted(set(re.findall(r'"(?:quotaMetric|quotaId)": "([^"]+)"', text))),
                              "quota_value": sorted(set(re.findall(r'"quotaValue": "([^"]+)"', text))),
                              "plain_call": plain}, ensure_ascii=False))
            continue
        resolved = []
        for c in got["chunks"][:3]:
            try:
                r = requests.head(c["uri"], allow_redirects=True, timeout=15)
                resolved.append({"title": c["title"], "final": r.url[:120], "status": r.status_code})
            except requests.RequestException as e:
                resolved.append({"title": c["title"], "error": type(e).__name__})
        print(json.dumps({
            "model": client.model, "seconds": round(time.monotonic() - started), "text_chars": len(got["text"]),
            "chunks": len(got["chunks"]), "supports": len(got["supports"]), "queries": got["queries"],
            "uri_sample": (got["chunks"][0]["uri"] or "")[:80] if got["chunks"] else None,
            "resolved": resolved,
            "lines": [{"text": s["text"][:120], "sources": [got["chunks"][i]["title"] for i in s["chunks"] if i < len(got["chunks"])]}
                      for s in got["supports"][:6]],
            "text": got["text"][:1500],
        }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
