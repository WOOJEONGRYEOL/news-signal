"""python3 -m newssignal <collect|build|serve|loop|doctor>"""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):  # tomllib 등 3.11 기능을 씁니다. macOS 기본 /usr/bin/python3(3.9)로 돌리면 여기서 멈춥니다.
    sys.exit(f"Python 3.11 이상이 필요합니다 (현재 {sys.version.split()[0]}). /opt/homebrew/bin/python3 을 쓰세요.")

import argparse
import http.server
import time
from functools import partial
from pathlib import Path

from . import __version__, now_kst
from .config import load
from .export import export_all, export_latest
from .store import Store


def cmd_collect(cfg, args) -> int:
    from .collect import run_collect
    store = Store(cfg.db_path)
    t0 = time.time()
    snap = run_collect(cfg, store, use_news_search=not args.no_search, verbose=args.verbose)
    store.save_snapshot(snap)
    export_latest(cfg, snap)
    today = snap["ts"][:10]
    dates = [today]
    prev = store.snapshot_dates()
    if len(prev) >= 2 and prev[-2] != today:
        dates.append(prev[-2])  # 자정 넘어간 직후엔 어제 파일도 갱신
    export_all(cfg, store, dates=dates)
    fails = snap["meta"]["failures"]
    print(f"[{snap['ts']}] 수집 완료 {time.time() - t0:.0f}s · 카테고리 {len(snap['categories'])} · "
          f"기사 말뭉치 {sum(snap['meta']['corpus'].values())}건 · 랭킹 {snap['meta']['ranking_rows']}건 · "
          f"지역 {snap['meta']['regions']}곳 · 실패 {len(fails)}")
    for f in fails:
        print("  ", f)
    top = snap["categories"].get("전체", [])[: cfg.top_n]
    print("  전체 Top:", " · ".join(f"{o['r']}.{o['k']}" for o in top))
    return 0


def cmd_build(cfg, args) -> int:
    store = Store(cfg.db_path)
    export_all(cfg, store)
    print("site/data 재생성 완료:", ", ".join(store.snapshot_dates()) or "(스냅샷 없음)")
    return 0


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *a):  # 조용히
        pass


def cmd_serve(cfg, args) -> int:
    handler = partial(_Handler, directory=str(cfg.site_dir))
    with http.server.ThreadingHTTPServer((args.host, args.port), handler) as httpd:
        print(f"대시보드: http://{args.host}:{args.port}/  (Ctrl+C로 종료)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def cmd_loop(cfg, args) -> int:
    every = args.every or cfg.interval_minutes
    print(f"{every}분마다 수집합니다. Ctrl+C로 종료.")
    while True:
        try:
            cmd_collect(cfg, args)
        except Exception as e:
            print("수집 실패:", e)
        time.sleep(every * 60)


def cmd_doctor(cfg, args) -> int:
    from .sources import google_news, google_trends, nate, naver, yna, zum
    now = now_kst()
    checks = [
        ("구글 트렌드 (전국)", lambda: google_trends.fetch_trends("KR")),
        ("구글 트렌드 (서울 KR-11)", lambda: google_trends.fetch_trends("KR-11")),
        ("네이버 랭킹뉴스", lambda: naver.fetch_ranking(now)),
        ("네이버 정치 섹션", lambda: naver.fetch_section("100", now)),
        ("연합뉴스 RSS (정치)", lambda: yna.fetch_yna("politics")),
        ("네이트 실시간 이슈", nate.fetch_nate),
        ("줌 AI 이슈트렌드", zum.fetch_zum),
        ("구글 뉴스 검색", lambda: google_news.search_news("날씨", 3)),
    ]
    bad = 0
    for name, fn in checks:
        try:
            r = fn()
            print(f"  ok   {name}: {len(r)}건")
        except Exception as e:
            bad += 1
            print(f"  FAIL {name}: {e}")
    print("모두 정상" if not bad else f"{bad}개 출처 실패")
    return 1 if bad else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="newssignal", description=f"News Signal v{__version__}")
    p.add_argument("--root", type=Path, default=None, help="프로젝트 루트(기본: 패키지 위치)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="지금 한 번 수집하고 site/data 갱신")
    c.add_argument("--no-search", action="store_true", help="구글 뉴스 검색 보강 생략")
    c.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("build", help="DB에서 site/data 전부 다시 생성")
    s = sub.add_parser("serve", help="로컬 웹서버로 대시보드 열기")
    s.add_argument("--port", type=int, default=8770)
    s.add_argument("--host", default="127.0.0.1")
    l = sub.add_parser("loop", help="N분마다 수집 반복(포그라운드)")
    l.add_argument("--every", type=int, default=None)
    l.add_argument("--no-search", action="store_true")
    l.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("doctor", help="출처별 연결 상태 점검")
    args = p.parse_args(argv)
    cfg = load(args.root)
    return {"collect": cmd_collect, "build": cmd_build, "serve": cmd_serve, "loop": cmd_loop, "doctor": cmd_doctor}[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
