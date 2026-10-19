# -*- coding: utf-8 -*-
"""공통 설정: 신문사 목록, 경로, HTTP 세션."""
import os
from pathlib import Path

# 신문사 oid → 이름 (네이버 언론사 식별자)
# 중앙SUNDAY(353)는 토요일만 발행 — 평일엔 지면이 없어 자동으로 건너뜀
PRESSES = {
    "023": "조선일보",
    "025": "중앙일보",
    "353": "중앙SUNDAY",
    "020": "동아일보",
    "009": "매일경제",
    "015": "한국경제",
}

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
PAPERS_DIR = DATA_DIR / "papers"
SERIES_DIR = DATA_DIR / "series"
STATE_DIR = DATA_DIR / "state"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

NEWSPAPER_URL = "https://media.naver.com/press/{oid}/newspaper?date={date}"
SEARCH_URL = "https://search.naver.com/search.naver?where=news&query={query}"

# 텔레그램 (GitHub Secrets / .env 로만 주입 — 코드에 값 금지)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 워치 키워드: 제목에 매칭되면 다이제스트 최상단 '관심 기사' 섹션으로 올라감.
# 환경변수 WATCH_KEYWORDS(쉼표 구분)로 교체 가능 — 이관 시 상대 조직 키워드로 바꾸면 됨.
WATCH_KEYWORDS = [
    k.strip()
    for k in os.environ.get(
        "WATCH_KEYWORDS",
        "SK,SK브로드밴드,SKB,SK텔레콤,SKT,SK하이닉스,SK수펙스,최태원,최창원",
    ).split(",")
    if k.strip()
]
WATCH_LABEL = os.environ.get("WATCH_LABEL", "SK 관련")


def make_session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def get(session, url, timeout=20):
    """사내망 등 SSL 검증 문제 시 1회에 한해 verify=False 로 재시도."""
    import requests

    try:
        r = session.get(url, timeout=timeout)
    except requests.exceptions.SSLError:
        import urllib3

        urllib3.disable_warnings()
        r = session.get(url, timeout=timeout, verify=False)
    r.raise_for_status()
    return r


def kst_today():
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
