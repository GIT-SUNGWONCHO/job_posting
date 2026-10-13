"""명령줄 실행: uv run jobpost collect --data-dir data, uv run jobpost screen --data-dir data --out screen.json.gz"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import ai, db, pipeline, publish, recommend, screen


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
        client = ai.Gemini() if ai.configured() else None
        summary = recommend.run(built, bodies, db.DB(), client, date.today())
        json.dump(summary, sys.stdout, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
