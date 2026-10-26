# -*- coding: utf-8 -*-
"""네이버 지면보기(media.naver.com/press/{oid}/newspaper)에서 5개사 전 지면 수집."""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

try:
    from . import config
except ImportError:
    import config


def parse_newspaper(html, oid, date):
    """지면 페이지 HTML → 기사 리스트. 면(brick) 단위로 순회."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    for brick in soup.select("div.newspaper_brick_item"):
        notation = brick.select_one("span.page_notation em")
        if not notation:
            continue
        page = notation.get_text(strip=True)  # e.g. "A1"
        for order, li in enumerate(brick.select("ul.newspaper_article_lst > li"), start=1):
            a = li.select_one("a[href]")
            if not a:
                continue
            href = a["href"]
            m = re.search(r"/article/(?:newspaper/)?(\d+)/(\d+)", href)
            if not m:
                continue
            article_id = m.group(2)
            strong = a.select_one("strong")
            title = strong.get_text(" ", strip=True) if strong else a.get_text(" ", strip=True)
            img = a.select_one("img[src]")
            articles.append(
                {
                    "press": oid,
                    "pressName": config.PRESSES.get(oid, oid),
                    "date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
                    "page": page,
                    "pageOrder": order,
                    "isTop": order == 1,
                    "hasThumbnail": img is not None,
                    "thumb": img["src"] if img else None,
                    "column": None,  # enrich.py 에서 보강
                    "title": title,
                    "url": f"https://n.news.naver.com/article/{oid}/{article_id}",
                    "articleId": article_id,
                    "seriesKey": None,  # series.py 에서 채움
                    "seriesType": None,
                }
            )
    return articles


def page_sort_key(page):
    """면 정렬: 알파벳 섹션(A,B,...) → 숫자. 'A10' > 'A2' 문제 방지."""
    m = re.match(r"([A-Za-z]*)(\d+)", page)
    if not m:
        return ("Z", 999)
    return (m.group(1) or "A", int(m.group(2)))


def collect_date(session, date, existing=None):
    """하루치 5개사 수집. existing(기존 JSON)이 있으면 column 등 보강값 보존하며 upsert."""
    prev = {}
    if existing:
        for a in existing.get("articles", []):
            prev[(a["press"], a["articleId"])] = a

    all_articles = []
    stats = {}
    for oid in config.PRESSES:
        url = config.NEWSPAPER_URL.format(oid=oid, date=date)
        try:
            r = config.get(session, url)
            arts = parse_newspaper(r.text, oid, date)
        except Exception as e:
            print(f"  [WARN] {config.PRESSES[oid]}({oid}) 수집 실패: {e}", file=sys.stderr)
            arts = [a for a in prev.values() if a["press"] == oid]  # 기존 데이터 유지
        for a in arts:
            old = prev.get((a["press"], a["articleId"]))
            if old:
                for k in ("column", "seriesKey", "seriesType", "related", "searchDone"):
                    if old.get(k) is not None:
                        a[k] = old[k]
        # 검색 보강(search_backfill.py)으로 추가된 기사는 지면보기에 없으므로 유지
        ids = {a["articleId"] for a in arts}
        arts.extend(
            a
            for a in prev.values()
            if a["press"] == oid and a.get("source") == "search" and a["articleId"] not in ids
        )
        all_articles.extend(arts)
        stats[config.PRESSES[oid]] = len(arts)
        time.sleep(0.8)

    all_articles.sort(key=lambda a: (a["press"], page_sort_key(a["page"]), a["pageOrder"]))
    return all_articles, stats


def save_date(date, articles):
    config.PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    path = config.PAPERS_DIR / f"{iso}.json"
    doc = {
        "date": iso,
        "collectedAt": datetime.now().isoformat(timespec="seconds"),
        "articles": articles,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def update_manifest():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    dates = sorted(p.stem for p in config.PAPERS_DIR.glob("*.json"))
    (config.DATA_DIR / "manifest.json").write_text(
        json.dumps(
            # pressOrder: JS 객체 키는 숫자형("469" 등) 순서가 바뀌므로 배열로 순서 고정
            {"dates": dates, "presses": config.PRESSES, "pressOrder": list(config.PRESSES)},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def load_existing(date):
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    path = config.PAPERS_DIR / f"{iso}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD (기본: KST 오늘)")
    ap.add_argument("--days", type=int, default=1, help="date부터 거슬러 올라갈 일수(백필)")
    args = ap.parse_args()

    base = args.date or config.kst_today()
    session = config.make_session()
    for i in range(args.days):
        d = (datetime.strptime(base, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
        existing = load_existing(d)
        arts, stats = collect_date(session, d, existing)
        if not arts:
            print(f"{d}: 기사 없음(휴간일 가능) — 저장 생략")
            continue
        path = save_date(d, arts)
        print(f"{d}: {sum(stats.values())}건 저장 → {path.name} {stats}")
    update_manifest()


if __name__ == "__main__":
    main()
