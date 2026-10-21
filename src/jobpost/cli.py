"""명령줄 실행: uv run jobpost collect --data-dir data, uv run jobpost screen --data-dir data --out screen.json.gz"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import ai, config, db, facts, feedback, notify, pipeline, publish, recommend, screen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobpost")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="공고를 수집해 data 폴더에 쌓는다")
    c.add_argument("--data-dir", type=Path, default=Path("data"))
    c.add_argument("--sources", help="쉼표로 구분(zighang,remember,saramin). 생략하면 전부")
    c.add_argument("--max-pages", type=int, help="시험용: 조회마다 최대 페이지 수")
    c.add_argument("--detail-budget", type=int, help="직행 상세를 받을 최대 건수")

    s = sub.add_parser("screen", help="화면용 파일(오늘 열린 국내 공고 + 회사)을 만든다")
    s.add_argument("--data-dir", type=Path, default=Path("data"))
    s.add_argument("--out", type=Path, default=Path("screen.json.gz"))
    s.add_argument("--upload", action="store_true",
                   help="Supabase 저장소에 올린다(환경 변수 SUPABASE_URL, SUPABASE_SECRET_KEY가 있을 때)")

    m = sub.add_parser("match", help="사람마다 매칭 점수와 매칭 이유를 Supabase에 쓴다")
    m.add_argument("--data-dir", type=Path, default=Path("data"))
    m.add_argument("--sample", action="store_true", help="기준 샘플(config/match_sample.yaml)만 다시 매긴다")
    m.add_argument("--model", help="이번 실행만 다른 모델로(회차 시험)")

    f = sub.add_parser("facts", help="후보 공고의 매칭 항목을 AI로 정리해 data 폴더 facts.jsonl에 쌓는다")
    f.add_argument("--data-dir", type=Path, default=Path("data"))

    r = sub.add_parser("feedback", help="회차 리포트: 내 평가와 그때의 AI 판단 근거를 로그로 낸다")
    r.add_argument("--data-dir", type=Path, default=Path("data"))

    n = sub.add_parser("notify", help="아침 알림: 연결한 사람마다 새 공고 요약을 보낸다(채널은 config/notify.yaml)")
    n.add_argument("--data-dir", type=Path, default=Path("data"))
    n.add_argument("--telegram-connect", action="store_true",
                   help="텔레그램 연결: 봇에게 최근에 /start를 보낸 대화방을 저장한 뒤 바로 보낸다")
    n.add_argument("--kakao-code", metavar="CODE", help="카톡 연결: 인가 코드로 토큰을 받아 저장한 뒤 바로 보낸다")
    n.add_argument("--user-id", help="연결할 사람(프로필이 여럿일 때)")
    n.add_argument("--again", action="store_true", help="오늘 이미 보냈어도 다시 보낸다(모양 확인용)")

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
    if args.cmd == "screen":
        built, bodies = screen.build(args.data_dir)
        path = screen.write(built, args.out)
        body_paths = screen.write_bodies(bodies, args.out.parent)
        logging.info("화면용 파일: 공고 %d건, 회사 %d곳, %s KB / 본문 %d건, %d개 파일 %s KB",
                     built["counts"]["open"], built["counts"]["companies"], path.stat().st_size // 1024,
                     len(bodies["bodies"]), len(body_paths), sum(p.stat().st_size for p in body_paths) // 1024)
        if args.upload:
            if not publish.configured():
                logging.info("Supabase 설정이 없어 올리지 않음")
            else:
                publish.upload(path)
                for bp in body_paths:
                    publish.upload(bp, name=f"bodies/{bp.name}")
                logging.info("Supabase 저장소에 올림")
    if args.cmd == "match":
        if not db.configured():
            logging.info("Supabase 설정이 없어 매칭을 건너뜀")
            return 0
        built, bodies = screen.build(args.data_dir)
        store = db.DB()
        store.check_server_key()
        only = set(recommend.sample_ids()) if args.sample else None
        summary = recommend.run(built, bodies, store, recommend.make_client(args.model), date.today(),
                                facts.load(args.data_dir), only=only)
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
    if args.cmd == "facts":
        built, bodies = screen.build(args.data_dir)
        settings: list[dict] = []
        if db.configured():
            store = db.DB()
            store.check_server_key()
            settings = store.select("settings", "select=user_id,filters")
        wanted = facts.candidates_for_all(built, settings)
        client = ai.Gemini() if ai.configured() else None
        summary = facts.run(args.data_dir, built, bodies, wanted, client, date.today().isoformat())
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
        print("\n".join(feedback.report(sample, matches, rows) + feedback.sample_dump(sample, matches, rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
