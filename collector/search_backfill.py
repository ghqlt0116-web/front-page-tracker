# -*- coding: utf-8 -*-
"""지면보기 미등록 기사 검색 보강.

신문사가 인쇄지면의 모든 기사를 네이버 지면보기에 등록하지는 않는다
(예: 2026-10-19 조선일보 A6면 특별감찰관 기사). 하지만 네이버 뉴스검색
결과에는 'A6면 1단' 지면 배지가 붙어 노출되므로, 1면 기사 본문의
주제어를 쿼리로 삼아 같은 날짜·같은 신문사의 미수집 지면 기사를 찾아
papers JSON에 추가한다 (source="search" 플래그, pageOrder는 기존 뒤).

요청량: 1면 기사당 검색 1회(searchDone 플래그로 재실행 시 생략),
하루 25회 내외 + 발견 기사당 본문 1회. 차단 감지 시 즉시 중단하고
그때까지의 데이터는 유지한다.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime

try:
    from . import config, enrich, related
except ImportError:
    import config
    import enrich
    import related

# 날짜 한정(pd=3&ds/de) + 지면기사 유형(photo=3: 지면 배지 기사만 노출, 실측)
# + 언론사 필터(news_office_checked="1"+oid, 간혹 무시되므로 파싱 때 oid로 재필터).
SEARCH_URL = (
    "https://search.naver.com/search.naver?where=news&query={query}"
    "&pd=3&ds={ds}&de={de}&photo=3"
    "&office_type=1&office_section_code=1&news_office_checked=1{oid}"
)

TITLE_RE = re.compile(r'property="og:title"\s+content="([^"]+)"')
DATETIME_RE = re.compile(r'data-date-time="(\d{4}-\d{2}-\d{2})')


def build_query(title, body_cnt):
    """1면 기사 제목 + 본문 빈출어로 검색 쿼리 구성."""
    title_tk = related.tokenize(re.sub(r"[\"'“”‘’\[\]()<>〈〉]", " ", title))
    # 제목에 있고 본문에서도 반복되는 단어 = 그 기사의 주제어
    anchors = [t for t in dict.fromkeys(title_tk) if body_cnt.get(t, 0) >= 2]
    anchors.sort(key=lambda t: (-body_cnt[t], -len(t)))
    q = anchors[:3]
    if len(q) < 2:
        q += [t for t, c in body_cnt.most_common(5) if c >= 3 and t not in q][: 2 - len(q)]
    if not q:
        q = title_tk[:2]
    return " ".join(q)


def extract_badged(html, oid):
    """검색 결과에서 (지면 배지 → 해당 아이템의 네이버 기사링크) 쌍 추출 → {aid: (면, 단)}.

    [실측] 검색 결과 HTML 은 아이템마다 배지가 기사 링크보다 200~900자
    '앞'에 오므로, 배지 뒤 2500자 안의 첫 기사 링크와 짝짓는다.
    (enrich.find_column 의 ±4000자 창은 인접 아이템의 배지를 집을 수 있음)
    """
    out = {}
    link_re = re.compile(rf"article/{oid}/(\d{{9,10}})")
    for b in enrich.BADGE.finditer(html):
        m = link_re.search(html, b.end(), b.end() + 2500)
        if m:
            out.setdefault(m.group(1), (b.group(1), int(b.group(2))))
    return out


def fetch_article_meta(session, oid, aid):
    """기사 페이지에서 제목·발행일·(있으면) 지면 배지 추출."""
    r = config.get(session, f"https://n.news.naver.com/article/{oid}/{aid}")
    head = r.text[:80000]
    m = TITLE_RE.search(head)
    title = m.group(1).strip() if m else None
    d = DATETIME_RE.search(head)
    pub_date = d.group(1) if d else None
    b = enrich.BADGE.search(head)
    page = b.group(1) if b else None
    return title, pub_date, page


def make_record(oid, date_iso, aid, title, page, col, order):
    return {
        "press": oid,
        "pressName": config.PRESSES.get(oid, oid),
        "date": date_iso,
        "page": page,
        "pageOrder": order,
        "isTop": False,
        "hasThumbnail": False,
        "thumb": None,
        "column": col,
        "title": title,
        "url": f"https://n.news.naver.com/article/{oid}/{aid}",
        "articleId": aid,
        "seriesKey": None,
        "seriesType": None,
        "related": None,
        "source": "search",
    }


def backfill_file(session, path, delay=1.5, max_searches=25, body_cache=None):
    """1면 주제어 검색으로 미등록 지면 기사 추가. (searched, added, blocked) 반환.

    body_cache({articleId: 본문 주제어 set})를 넘기면 수집한 1면 본문
    토큰을 채워줘서 이어지는 related.relate_file 이 본문을 재요청하지 않는다.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    date_iso = doc["date"]
    ds = date_iso.replace("-", ".")
    arts = doc["articles"]

    by_press = {}
    for a in arts:
        by_press.setdefault(a["press"], []).append(a)

    searched = added = 0
    blocked = False
    changed = False

    for oid, press_arts in by_press.items():
        if blocked:
            break
        main = related.main_front_sec(press_arts)
        if main is None:
            continue
        fronts = [a for a in press_arts if related.page_parts(a["page"]) == (main, 1)]
        known = {a["articleId"] for a in press_arts}
        # 같은 면에 기사를 2건 이상 추가할 때 pageOrder 가 겹치지 않도록
        page_max_order = {}
        for a in press_arts:
            page_max_order[a["page"]] = max(page_max_order.get(a["page"], 0), a["pageOrder"])
        press_added = 0

        for art in fronts:
            if blocked or searched >= max_searches:
                break
            if art.get("searchDone"):
                continue
            try:
                cnt = related.fetch_body_counter(session, art["url"])
            except Exception as e:
                print(f"  [WARN] 본문 수집 실패({art['articleId']}): {e}", file=sys.stderr)
                continue
            if body_cache is not None:
                body_cache[art["articleId"]] = related.topic_tokens(cnt)
            query = build_query(art["title"], cnt)
            if not query:
                art["searchDone"] = True
                changed = True
                continue
            url = SEARCH_URL.format(query=urllib.parse.quote(query), ds=ds, de=ds, oid=oid)
            try:
                r = config.get(session, url)
            except Exception as e:
                print(f"  [WARN] 검색 실패({query!r}): {e}", file=sys.stderr)
                continue
            finally:
                searched += 1
                time.sleep(delay)
            if enrich.is_blocked(r.text):
                print("  [WARN] 검색 차단 감지 — 보강 중단(기존 데이터 유지)", file=sys.stderr)
                blocked = True
                break
            art["searchDone"] = True
            changed = True

            for aid, (page, col) in extract_badged(r.text, oid).items():
                if aid in known:
                    continue
                try:
                    title, pub_date, page2 = fetch_article_meta(session, oid, aid)
                    time.sleep(delay)
                except Exception as e:
                    print(f"  [WARN] 기사 확인 실패({aid}): {e}", file=sys.stderr)
                    continue
                known.add(aid)
                if not title:
                    continue
                # 날짜 필터가 무시됐을 때 과거 기사 유입 방지 (지면 기사는
                # 보통 당일 00~05시, 드물게 전날 밤 온라인 선공개)
                if pub_date and not _pub_date_ok(pub_date, date_iso):
                    continue
                if page2:
                    page = page2  # 기사 페이지의 지면 표기가 더 정확
                order = page_max_order.get(page, 0) + 1
                page_max_order[page] = order
                arts.append(make_record(oid, date_iso, aid, title, page, col, order))
                added += 1
                press_added += 1

        if press_added:
            # 새 기사가 매칭 풀에 들어가도록 이 신문사 1면의 related 재계산 유도
            for art in fronts:
                art["related"] = None
            changed = True

    if changed or added:
        arts.sort(key=lambda a: (a["press"], _page_key(a["page"]), a["pageOrder"]))
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return searched, added, blocked


def _pub_date_ok(pub_date, paper_date):
    try:
        delta = (
            datetime.strptime(paper_date, "%Y-%m-%d") - datetime.strptime(pub_date, "%Y-%m-%d")
        ).days
    except ValueError:
        return True
    return 0 <= delta <= 1


def _page_key(page):
    m = re.match(r"([A-Za-z]*)(\d+)", page)
    if not m:
        return ("Z", 999)
    return (m.group(1) or "A", int(m.group(2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 최근 파일)")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--max", type=int, default=25)
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
        s, a, b = backfill_file(session, p, delay=args.delay, max_searches=args.max)
        print(f"{p.name}: 검색 {s}회, 지면기사 {a}건 추가" + (" (차단으로 중단)" if b else ""))


if __name__ == "__main__":
    main()
