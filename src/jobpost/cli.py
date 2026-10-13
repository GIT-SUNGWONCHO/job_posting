"""명령줄 실행: uv run jobpost collect --data-dir data"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobpost")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="공고를 수집해 data 폴더에 쌓는다")
    c.add_argument("--data-dir", type=Path, default=Path("data"))
    c.add_argument("--sources", help="쉼표로 구분(zighang,remember,saramin). 생략하면 전부")
    c.add_argument("--max-pages", type=int, help="시험용: 조회마다 최대 페이지 수")
    c.add_argument("--detail-budget", type=int, help="직행 상세를 받을 최대 건수")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
