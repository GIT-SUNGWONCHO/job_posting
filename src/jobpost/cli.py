"""명령줄 실행: uv run jobpost collect --data-dir data, uv run jobpost screen --data-dir data --out screen.json.gz"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import (
    ai,
    config,
    dart,
    db,
    facts,
    feedback,
    notes,
    notify,
    pipeline,
    publish,
    recommend,
    screen,
)


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
        print("\n".join(feedback.report(sample, matches, rows) + feedback.sample_dump(sample, matches, rows)))
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
