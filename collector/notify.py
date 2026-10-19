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


import re as _re


def _page_parts(page):
    m = _re.match(r"([A-Za-z]*)0*(\d+)$", page)
    return (m.group(1).upper(), int(m.group(2))) if m else ("Z", 999)


SHORT_NAMES = {
    "023": "조선",
    "025": "중앙",
    "353": "선데이",
    "020": "동아",
    "009": "매경",
    "015": "한경",
}


def cut(s, n=40):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _watch_regexes():
    regs = []
    for k in config.WATCH_KEYWORDS:
        if _re.fullmatch(r"[A-Za-z0-9&.\- ]+", k):
            # 영문 키워드는 단어 경계 적용 ('SK'가 'TASK' 등에 걸리지 않게)
            regs.append(_re.compile(r"(?<![A-Za-z])" + _re.escape(k) + r"(?![A-Za-z])", _re.I))
        else:
            regs.append(_re.compile(_re.escape(k)))
    return regs


def watch_lines(doc):
    """워치 키워드 매칭 기사 — 전 지면 대상, 다이제스트 최상단에 표시."""
    regs = _watch_regexes()
    lines, ids = [], []
    for a in doc["articles"]:
        if any(r.search(a["title"]) for r in regs):
            short = SHORT_NAMES.get(a["press"], a["pressName"])
            lines.append(
                f"🔺 <b>{esc(short)}</b> {esc(a['page'])}면 · <a href=\"{a['url']}\">{esc(cut(a['title']))}</a>"
            )
            ids.append(a["articleId"])
    return lines[:10], ids


def front_page_lines(doc, skip_ids=()):
    """머리기사는 매체당 한 줄, 나머지 1면 기사는 접히는 블록용으로 분리.

    A섹션이 없는 매체(중앙SUNDAY=T1)도 처리. skip_ids(워치 섹션에 이미 노출된
    기사)는 접힘 블록에서 제외해 중복을 줄인다.
    """
    by_press = {}
    for a in doc["articles"]:
        by_press.setdefault(a["press"], []).append(a)
    out = {}
    for oid, arts in by_press.items():
        secs = {_page_parts(a["page"])[0] for a in arts if _page_parts(a["page"])[1] == 1}
        if not secs:
            continue
        main = "A" if "A" in secs else ("" if "" in secs else sorted(secs)[0])
        out[oid] = [a for a in arts if _page_parts(a["page"]) == (main, 1)]
    tops, rest, ids = [], [], []
    for oid in config.PRESSES:
        arts = out.get(oid)
        if not arts:
            continue
        arts = sorted(arts, key=lambda a: a["pageOrder"])
        short = SHORT_NAMES.get(oid, config.PRESSES[oid])
        top = arts[0]
        tops.append(f"<b>{esc(short)}</b> <a href=\"{top['url']}\">{esc(cut(top['title']))}</a>")
        for a in arts[1:]:
            if a["articleId"] in skip_ids:
                continue
            rest.append(f"{esc(short)} · <a href=\"{a['url']}\">{esc(cut(a['title']))}</a>")
        ids.extend(a["articleId"] for a in arts)
    lines = tops
    if rest:
        # 탭하면 펼쳐지는 인용 블록 — 기본 화면은 머리기사만 보인다
        lines = tops + ["", "<blockquote expandable>📄 1면의 다른 기사들\n" + "\n".join(rest) + "</blockquote>"]
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

    w_lines, w_ids = watch_lines(doc)
    fp_lines, fp_ids = front_page_lines(doc, skip_ids=set(w_ids))
    sr_lines, sr_ids = series_lines(index, date)

    # 중복 발송 방지 (2차 실행)
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = config.STATE_DIR / f"notify_{date}.json"
    sent = set(json.loads(state_path.read_text(encoding="utf-8"))["ids"]) if state_path.exists() else set()
    new_ids = [i for i in w_ids + fp_ids + sr_ids if i not in sent]
    if sent and not new_ids:
        print("추가 발송할 신규 항목 없음")
        return

    y, m, d = date.split("-")
    header = f"🗞 <b>{y}.{m}.{d} 조간 가판대</b>" + (" (추가분)" if sent else "")
    body = [header, ""]
    if w_lines:
        body += [f"<b>{esc(config.WATCH_LABEL)}</b>"] + w_lines + [""]
    body += fp_lines
    if sr_lines:
        body += ["📑 <b>기획 시리즈</b>", ""] + sr_lines
    # 대시보드 링크: Actions 환경변수(owner/repo)에서 Pages 주소를 유도 — 이관 후에도 자동
    repo = os_environ_repo()
    if repo:
        owner, name = repo.split("/", 1)
        body += ["", f"📊 <a href=\"https://{owner}.github.io/{name}/\">대시보드 열기</a>"]
    ok = send("\n".join(body))
    if ok:
        # 발송 성공시에만 기록: 실패하면 2차 실행(07:00)이 그대로 재시도한다
        state_path.write_text(
            json.dumps({"ids": sorted(set(list(sent) + w_ids + fp_ids + sr_ids))}, ensure_ascii=False),
            encoding="utf-8",
        )
    print("발송 완료" if ok else "발송 실패/생략")


def os_environ_repo():
    import os

    return os.environ.get("GITHUB_REPOSITORY", "")


if __name__ == "__main__":
    main()
