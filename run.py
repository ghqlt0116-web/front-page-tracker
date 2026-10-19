# -*- coding: utf-8 -*-
"""일일 파이프라인: 수집 → 면·단 보강 → 시리즈 재구축 → (옵션) 텔레그램 발송.

사용:
  python run.py                     # KST 오늘 수집 + 전체 파이프라인
  python run.py --date 20261001 --days 14   # 백필
  python run.py --notify            # 마지막에 텔레그램 다이제스트 발송
  python run.py --skip-enrich       # 면·단 보강 생략
"""
import argparse
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "collector"))

import collect  # noqa: E402
import config  # noqa: E402
import enrich  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD (기본: KST 오늘)")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--enrich", action="store_true", help="면 번호 교차검증용 (단 정보는 무의미 — enrich.py 주석 참조)")
    args = ap.parse_args()

    base = args.date or config.kst_today()
    session = config.make_session()

    # 1) 수집
    for i in range(args.days):
        d = (datetime.strptime(base, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
        existing = collect.load_existing(d)
        arts, stats = collect.collect_date(session, d, existing)
        if not arts:
            print(f"{d}: 기사 없음(휴간일 가능)")
            continue
        collect.save_date(d, arts)
        print(f"{d}: {sum(stats.values())}건 {stats}")
    collect.update_manifest()

    # 2) 면 번호 교차검증 (옵션)
    if args.enrich:
        iso = f"{base[:4]}-{base[4:6]}-{base[6:]}"
        p = config.PAPERS_DIR / f"{iso}.json"
        if p.exists():
            done, fail = enrich.enrich_file(session, p)
            print(f"면·단 보강: {done}건 성공, {fail}건 매칭 실패")

    # 3) 관련 지면 기사 매칭 (1면 기사 본문 수집, 오늘자만)
    import related

    iso = f"{base[:4]}-{base[4:6]}-{base[6:]}"
    p = config.PAPERS_DIR / f"{iso}.json"
    if p.exists():
        n = related.relate_file(p)
        print(f"관련기사 매칭: 본문 {n}건 수집")

    # 4) 시리즈 재구축
    import series

    series.rebuild()
    collect.update_manifest()

    # 4) 알림
    if args.notify:
        import notify

        sys.argv = ["notify"]
        notify.main()


if __name__ == "__main__":
    main()
