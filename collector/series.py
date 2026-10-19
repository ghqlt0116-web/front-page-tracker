# -*- coding: utf-8 -*-
"""전체 papers 데이터에서 시리즈 인덱스를 재구축하고, 기사에 seriesKey를 역주입."""
import json

try:
    from . import config, rules
except ImportError:
    import config
    import rules


def load_all_papers():
    docs = []
    for p in sorted(config.PAPERS_DIR.glob("*.json")):
        docs.append((p, json.loads(p.read_text(encoding="utf-8"))))
    return docs


def load_overrides():
    path = config.SERIES_DIR / "overrides.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"exclude": [], "forceType": {}, "merge": {}}


def rebuild():
    docs = load_all_papers()
    ov = load_overrides()
    series = {}  # key -> record
    hits = []  # (doc_idx, article_idx, key)

    for di, (_path, doc) in enumerate(docs):
        for ai, art in enumerate(doc["articles"]):
            sig = rules.series_signature(art["title"])
            if not sig:
                # 2차: 회차 표기가 없어도 기획성 키워드 라벨([창간기획 ○○] 등)은 시리즈로 등록
                sig = rules.plan_label_signature(art["title"])
            if not sig:
                continue
            key = rules.norm_key(art["press"], sig["name"])
            key = ov.get("merge", {}).get(key, key)
            if key in ov.get("exclude", []):
                continue
            rec = series.setdefault(
                key,
                {
                    "seriesKey": key,
                    "press": art["press"],
                    "pressName": art["pressName"],
                    "name": sig["name"],
                    "seriesType": None,
                    "status": "ongoing",
                    "episodes": [],
                },
            )
            rec["episodes"].append(
                {
                    "label": sig["epLabel"],
                    "ord": sig["ord"],
                    "isEnd": sig["isEnd"],
                    "date": art["date"],
                    "page": art["page"],
                    "column": art.get("column"),
                    "title": art["title"],
                    "url": art["url"],
                    "articleId": art["articleId"],
                }
            )
            hits.append((di, ai, key))

    # 에피소드 정리·분류
    for key, rec in series.items():
        eps = sorted(rec["episodes"], key=lambda e: (e["date"], e["ord"]))
        # 같은 기사 중복 제거
        seen, uniq = set(), []
        for e in eps:
            if e["articleId"] in seen:
                continue
            seen.add(e["articleId"])
            uniq.append(e)
        rec["episodes"] = uniq
        first_ord = min(e["ord"] for e in uniq)
        has_sjh = any(e["label"] in ("상", "중", "하") for e in uniq)
        rec["seriesType"] = ov.get("forceType", {}).get(key) or rules.classify(
            rec["name"], first_ord, has_sjh
        )
        rec["status"] = "completed" if any(e["isEnd"] for e in uniq) else "ongoing"
        rec["firstDate"] = uniq[0]["date"]
        rec["lastDate"] = uniq[-1]["date"]

    # 단일 회차 + 번호 1도 아닌 연재칼럼 추정건은 유지(데이터로 남김) — 대시보드에서 필터

    # 기사에 seriesKey/seriesType 역주입 후 papers 저장
    type_of = {k: r["seriesType"] for k, r in series.items()}
    for di, (_p, doc) in enumerate(docs):
        for art in doc["articles"]:
            art["seriesKey"] = None
            art["seriesType"] = None
    for di, ai, key in hits:
        art = docs[di][1]["articles"][ai]
        art["seriesKey"] = key
        art["seriesType"] = type_of.get(key)
    for path, doc in docs:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    # 인덱스 저장 (최근 게재순)
    config.SERIES_DIR.mkdir(parents=True, exist_ok=True)
    index = sorted(series.values(), key=lambda r: r["lastDate"], reverse=True)
    (config.SERIES_DIR / "index.json").write_text(
        json.dumps({"series": index}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    n_plan = sum(1 for r in index if r["seriesType"] == "기획")
    print(f"시리즈 {len(index)}건 (기획 {n_plan}, 연재칼럼 {len(index) - n_plan})")
    return index


if __name__ == "__main__":
    rebuild()
