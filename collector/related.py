# -*- coding: utf-8 -*-
"""관련 지면 기사 매칭 보강: 1면 기사의 '본문'까지 수집해 안쪽 면 기사와 연결.

인쇄지면의 '▶관련기사 N면' 표기는 네이버 디지털 본문에서 삭제돼 직접 추출이
불가하므로(실측), 1면 기사 본문의 핵심 단어와 안쪽 면 기사 제목의 겹침으로 추정한다.
제목만 쓰는 클라이언트 추정보다 재현율이 높다. 결과는 기사 레코드의 `related`에 저장.

대상: 각 매체 종합 1면 기사 (하루 25건 내외 본문 요청).
"""
import argparse
import collections
import json
import re
import sys
import time

try:
    from . import config
except ImportError:
    import config

BODY_RE = re.compile(r'id="dic_area"[^>]*>(.*?)</article>', re.S)
TOKEN_RE = re.compile(r"[^0-9A-Za-z가-힣]+")

STOPWORDS = set(
    """단독 속보 종합 오늘 내일 올해 지난해 이번 지난 최근 한국 우리 정부 대통령 국내 해외
    사진 포토 전망 논란 확대 강화 추진 발표 그래픽 관련 기자 뉴스 신문 보도 지면 위해 대해
    때문 경우 이상 이하 모두 지금 당시 이후 이전 통해 대한 가장 매일 아침 시작 계속 상황
    문제 결과 가능 필요 수준 규모 기준 중심 입장 의미 영향 분석 검토""".split()
)


def page_parts(page):
    m = re.match(r"([A-Za-z]*)0*(\d+)$", page)
    return (m.group(1).upper(), int(m.group(2))) if m else ("Z", 999)


def main_front_sec(arts):
    secs = {page_parts(a["page"])[0] for a in arts if page_parts(a["page"])[1] == 1}
    if not secs:
        return None
    return "A" if "A" in secs else ("" if "" in secs else sorted(secs)[0])


def tokenize(text):
    toks = []
    for t in TOKEN_RE.split(text):
        if 2 <= len(t) <= 12 and t not in STOPWORDS and not t.isdigit():
            toks.append(t)
    return toks


def fetch_body_counter(session, url):
    """기사 본문의 단어 빈도 Counter (검색 보강의 쿼리 구성에도 사용)."""
    r = config.get(session, url)
    m = BODY_RE.search(r.text)
    if not m:
        return collections.Counter()
    txt = re.sub(r"<[^>]+>", " ", m.group(1))
    return collections.Counter(tokenize(txt))


def topic_tokens(cnt):
    # 본문에서 2회 이상 등장한 단어 + 상위 빈출어 → 그 기사의 주제어로 간주
    return {t for t, c in cnt.most_common(40) if c >= 2}


def fetch_body_tokens(session, url):
    return topic_tokens(fetch_body_counter(session, url))


def relate_file(path, delay=0.6, max_fetch=40, body_cache=None):
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_press = {}
    for a in doc["articles"]:
        by_press.setdefault(a["press"], []).append(a)

    session = config.make_session()
    fetched = 0
    for press, arts in by_press.items():
        main = main_front_sec(arts)
        fronts = [a for a in arts if page_parts(a["page"]) == (main, 1)]
        inner = [a for a in arts if page_parts(a["page"]) != (main, 1)]
        for art in fronts:
            if art.get("related") is not None or fetched >= max_fetch:
                continue
            title_tk = set(tokenize(art["title"]))
            if body_cache is not None and art["articleId"] in body_cache:
                body_tk = body_cache[art["articleId"]]  # 검색 보강이 이미 수집
            else:
                try:
                    body_tk = fetch_body_tokens(session, art["url"])
                    fetched += 1
                    time.sleep(delay)
                except Exception as e:
                    print(f"  [WARN] 본문 수집 실패({art['articleId']}): {e}", file=sys.stderr)
                    continue
            scored = []
            for a in inner:
                tks = set(tokenize(a["title"]))
                st = len(tks & title_tk)  # 제목끼리 겹침 (강한 신호)
                sb = len(tks & body_tk)  # 1면 본문과 제목 겹침
                score = st * 2 + sb
                # 제목 겹침 1개 이상이거나, 본문 주제어와 3개 이상 겹칠 때만
                if (st >= 1 and score >= 3) or sb >= 3:
                    scored.append((score, a))
            scored.sort(key=lambda x: -x[0])
            art["related"] = [
                {"articleId": a["articleId"], "page": a["page"], "title": a["title"], "url": a["url"]}
                for _s, a in scored[:3]
            ]
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return fetched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 최근 파일)")
    ap.add_argument("--all", action="store_true", help="모든 날짜 백필")
    args = ap.parse_args()

    if args.all:
        paths = sorted(config.PAPERS_DIR.glob("*.json"))
    elif args.date:
        paths = [config.PAPERS_DIR / f"{args.date}.json"]
    else:
        paths = sorted(config.PAPERS_DIR.glob("*.json"))[-1:]
    for p in paths:
        if not p.exists():
            print(f"{p.name} 없음", file=sys.stderr)
            continue
        n = relate_file(p)
        print(f"{p.name}: 본문 {n}건 수집·매칭")


if __name__ == "__main__":
    main()
