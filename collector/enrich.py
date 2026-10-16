# -*- coding: utf-8 -*-
"""네이버 뉴스 검색 결과의 'A1면 1단' 배지로 면·단 정보 보강. (기본 파이프라인에서 제외)

[2026-10-16 실측 결론] 네이버 검색 배지의 '단' 값은 톱기사·사설·부고 가리지 않고
전부 '1단'으로 등록돼 있어 기사 크기 변별력이 없다 (언론사가 위치값을 일괄 입력).
따라서 기사 벨류는 지면 목록의 게재 순서(pageOrder=1 → 머리기사)와 썸네일 유무를
프록시로 사용하고, 이 모듈은 '면 번호 교차검증'이 필요할 때만 수동 실행한다.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse

try:
    from . import config, rules
except ImportError:
    import config
    import rules

BADGE = re.compile(r"([A-Za-z]?\d{1,2})면\s*(\d{1,2})단")


def find_column(html, article_id):
    """검색 결과 HTML에서 article_id 아이템 주변의 면·단 배지 추출."""
    for m in re.finditer(re.escape(article_id), html):
        window = html[max(0, m.start() - 4000): m.start() + 4000]
        b = BADGE.search(window)
        if b:
            return b.group(1), int(b.group(2))
    return None, None


def is_blocked(html):
    # 정상 결과 페이지는 200KB 이상. 차단/보안확인 페이지는 짧다.
    # (주의: 정상 페이지에도 'captcha' 문자열이 JS 번들명으로 포함되므로 문자열 검사 금지)
    return len(html) < 20000


def enrich_file(session, path, delay=1.5, max_requests=80):
    doc = json.loads(path.read_text(encoding="utf-8"))
    targets = [
        a
        for a in doc["articles"]
        if a.get("column") is None
        and (a["page"] in ("A1", "1") or rules.series_signature(a["title"]))
    ]
    if not targets:
        return 0, 0
    done = fail = 0
    blocked = False
    for a in targets[:max_requests]:
        if blocked:
            break
        # 괄호 라벨 포함 원제목이 매칭률이 높음. 따옴표류만 제거.
        q = re.sub(r"[\"'“”‘’]", " ", a["title"]).strip()
        url = config.SEARCH_URL.format(query=urllib.parse.quote(q))
        try:
            r = config.get(session, url)
            if is_blocked(r.text):
                print("  [WARN] 검색 차단 감지 — 면·단 보강 중단", file=sys.stderr)
                blocked = True
                break
            page, col = find_column(r.text, a["articleId"])
            if col:
                a["column"] = col
                if page:
                    a["page"] = page  # 검색 배지의 면 표기가 더 정규적
                done += 1
            else:
                fail += 1
        except Exception as e:
            print(f"  [WARN] 검색 실패({a['articleId']}): {e}", file=sys.stderr)
            fail += 1
        time.sleep(delay)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return done, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 가장 최근 파일)")
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    if args.date:
        paths = [config.PAPERS_DIR / f"{args.date}.json"]
    else:
        paths = sorted(config.PAPERS_DIR.glob("*.json"))[-1:]
    session = config.make_session()
    for p in paths:
        if not p.exists():
            print(f"{p.name} 없음", file=sys.stderr)
            continue
        done, fail = enrich_file(session, p, delay=args.delay)
        print(f"{p.name}: 면·단 보강 {done}건 성공, {fail}건 매칭 실패")


if __name__ == "__main__":
    main()
