# -*- coding: utf-8 -*-
"""텔레그램 다이제스트: 각사 1면 머리기사 + 오늘의 기획 시리즈 동향 (링크 포함).

같은 날 재실행(2차 수집) 시에는 state 파일과 비교해 '새로 생긴 것'만 추가 발송한다.
"""
import argparse
import html
import json
import sys

try:
    from . import config
except ImportError:
    import config

API = "https://api.telegram.org/bot{token}/sendMessage"


def esc(s):
    return html.escape(s, quote=False)


def front_page_lines(doc):
    """신문사별 1면 기사 (머리기사 먼저)."""
    out = {}
    for a in doc["articles"]:
        if a["page"] not in ("A1", "1", "01"):
            continue
        out.setdefault(a["press"], []).append(a)
    lines, ids = [], []
    for oid in config.PRESSES:
        arts = out.get(oid)
        if not arts:
            continue
        arts = sorted(arts, key=lambda a: a["pageOrder"])
        top = arts[0]
        col = f" ({top['column']}단)" if top.get("column") else ""
        lines.append(f"<b>{esc(top['pressName'])}</b>{col}")
        lines.append(f"· <a href=\"{top['url']}\">{esc(top['title'])}</a>")
        for a in arts[1:3]:
            lines.append(f"· <a href=\"{a['url']}\">{esc(a['title'])}</a>")
        lines.append("")
        ids.extend(a["articleId"] for a in arts)
    return lines, ids


def series_lines(index, date):
    """오늘 회차가 실린 '기획' 시리즈."""
    lines, ids = [], []
    for rec in index:
        if rec["seriesType"] != "기획":
            continue
        todays = [e for e in rec["episodes"] if e["date"] == date]
        if not todays:
            continue
        n = len(rec["episodes"])
        for e in todays:
            if e["ord"] == min(x["ord"] for x in rec["episodes"]) and n == 1:
                tag = "🆕 시리즈 시작"
            elif e["isEnd"]:
                tag = "🏁 완결"
            else:
                tag = f"▶ {n}회차"
            where = e["page"] + (f" {e['column']}단" if e.get("column") else "")
            lines.append(f"{tag} <b>[{esc(rec['name'])}]</b> ({esc(rec['pressName'])}, {where}면)".replace("면면", "면"))
            lines.append(f"· ({esc(e['label'])}) <a href=\"{e['url']}\">{esc(e['title'])}</a>")
            ids.append(e["articleId"])
    return lines, ids


def send(text):
    import requests

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — 발송 생략", file=sys.stderr)
        print(text)
        return False
    url = API.format(token=config.TELEGRAM_BOT_TOKEN)
    # 텔레그램 메시지 한도 4096자 — 넘으면 분할
    chunks, cur = [], []
    size = 0
    for line in text.split("\n"):
        if size + len(line) > 3800:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    chunks.append("\n".join(cur))
    for c in chunks:
        r = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": c,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if not r.ok:
            print(f"[ERROR] 텔레그램 발송 실패: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 최근 파일)")
    args = ap.parse_args()

    paths = sorted(config.PAPERS_DIR.glob("*.json"))
    if not paths:
        print("데이터 없음", file=sys.stderr)
        return
    path = config.PAPERS_DIR / f"{args.date}.json" if args.date else paths[-1]
    doc = json.loads(path.read_text(encoding="utf-8"))
    date = doc["date"]

    idx_path = config.SERIES_DIR / "index.json"
    index = json.loads(idx_path.read_text(encoding="utf-8"))["series"] if idx_path.exists() else []

    fp_lines, fp_ids = front_page_lines(doc)
    sr_lines, sr_ids = series_lines(index, date)

    # 중복 발송 방지 (2차 실행)
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = config.STATE_DIR / f"notify_{date}.json"
    sent = set(json.loads(state_path.read_text(encoding="utf-8"))["ids"]) if state_path.exists() else set()
    new_ids = [i for i in fp_ids + sr_ids if i not in sent]
    if sent and not new_ids:
        print("추가 발송할 신규 항목 없음")
        return

    y, m, d = date.split("-")
    header = f"🗞 <b>{y}.{m}.{d} 조간 1면</b>" + (" (추가분)" if sent else "")
    body = [header, ""]
    body += fp_lines
    if sr_lines:
        body += ["📑 <b>기획 시리즈</b>", ""] + sr_lines
    ok = send("\n".join(body))
    if ok or not sent:
        state_path.write_text(
            json.dumps({"ids": sorted(set(list(sent) + fp_ids + sr_ids))}, ensure_ascii=False),
            encoding="utf-8",
        )
    print("발송 완료" if ok else "발송 실패/생략")


if __name__ == "__main__":
    main()
