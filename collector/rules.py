# -*- coding: utf-8 -*-
"""기획 시리즈 감지 규칙.

5개사(조선·중앙·동아·매경·한경) 실제 지면 제목 2,879건 조사를 바탕으로 작성.
관찰된 스타일:
  - 조선: [코너명] [10] 제목          (더블 브래킷, 회차 선두)
  - 동아: 제목 [코너명]〈426〉        (말미형)
  - 공통: [기획명] (상) 제목, 기획명 (下), [르포] 제목 ①, ... ·끝
"""
import re
import unicodedata

# ── 괄호류 ────────────────────────────────────────────────────────────
OPEN = r"[\[\(〈<【「《]"
CLOSE = r"[\]\)〉>】」》]"

# ── 회차 토큰 ─────────────────────────────────────────────────────────
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
SJH = {"상": 1, "중": 2, "하": 3, "上": 1, "中": 2, "下": 3}
ROMAN = {"Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "Ⅴ": 5, "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}

# 괄호 안 회차: (상) [3] 〈426〉 (2부) (제3화) (Ⅱ) (끝)
_EP_IN_BRACKET = re.compile(
    OPEN + r"\s*(?:"
    r"(?P<sjh>[상중하上中下])(?:\s*[·/]\s*끝)?"
    r"|(?P<num>\d{1,3})"
    r"|제?\s*(?P<unit_n>\d{1,2})\s*(?P<unit>[부회편화탄])"
    r"|(?P<roman>Ⅰ|Ⅱ|Ⅲ|Ⅳ|Ⅴ|IV|III|II|I|V)"
    r"|(?P<end>끝|完)"
    r")\s*" + CLOSE
)
# 괄호 없는 종결: "... ·끝", "... -끝", "... ·끝· ..."
_EP_DOT_END = re.compile(r"[·\-—]\s*끝\s*(?:[·\-—]|$)")
# 원문자 회차
_EP_CIRCLED = re.compile("([" + CIRCLED + "])")
# 제목 선두/말미의 비괄호 회차: "AI 대전환 2부", "2부 제목" (중간 등장 "운행 8회 늘린다"는 제외)
_EP_EDGE_UNIT = re.compile(r"(?:^|\s)제?(\d{1,2})(부|회|편|화|탄)(?:\s*[:：·,]|\s|$)")

# ── 제외 라벨(고정 지면물·코너) ──────────────────────────────────────
EXCLUDE_LABEL = re.compile(
    r"^(포토|사설|기고|특별기고|기자24시|알림|부고|인사|부음|단독|속보|종합|만평|만화|날씨|"
    r"오늘의\s?운세|신문과\s?놀자|독자\s?편지|바로잡습니다|MBN|TV|팩트체크)$"
)
EXCLUDE_ANY = re.compile(r"(기왕전|프로기전|명인전|국수전|왕위전|십단전|바둑|장학퀴즈|오늘의\s?날씨)")

# ── 기획/연재칼럼 분류 ───────────────────────────────────────────────
PLAN_KEYWORDS = re.compile(
    r"(기획|시리즈|르포|프로젝트|진단|해부|대해부|리포트|보고서|특집|심층|추적|어젠다|"
    r"대전환|대예측|제언|긴급점검|점검|현장|위기|보고|돋보기|팩트|이슈|쟁점|심층취재|"
    r"신년|창간|연중|광복|순례|탐사|분석)"
)
PERSONAL_COLUMN = re.compile(r"^[가-힣]{2,5}(의|와|과)\s")  # "우정아의 아트 스토리"


def _norm(s):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return s.lower()


def extract_episode(title):
    """제목에서 회차 토큰 추출 → (ord, label, is_end, span) / 없으면 None.

    ord: 정렬용 숫자(상=1 중=2 하=3, 끝=9999), label: 표시용("상", "3", "2부", "끝")
    """
    m = _EP_IN_BRACKET.search(title)
    if m:
        if m.group("sjh"):
            v = m.group("sjh")
            return SJH[v], {"上": "상", "中": "중", "下": "하"}.get(v, v), v in ("하", "下"), m.span()
        if m.group("num"):
            n = int(m.group("num"))
            return n, str(n), False, m.span()
        if m.group("unit_n"):
            n = int(m.group("unit_n"))
            return n, f"{n}{m.group('unit')}", False, m.span()
        if m.group("roman"):
            n = ROMAN[m.group("roman")]
            return n, m.group("roman"), False, m.span()
        if m.group("end"):
            return 9999, "끝", True, m.span()
    m = _EP_DOT_END.search(title)
    if m:
        return 9999, "끝", True, m.span()
    m = _EP_CIRCLED.search(title)
    if m:
        n = CIRCLED.index(m.group(1)) + 1
        return n, m.group(1), False, m.span()
    m = _EP_EDGE_UNIT.search(title)
    if m and (m.start() < 2 or m.end() > len(title) - 2):
        n = int(m.group(1))
        return n, f"{n}{m.group(2)}", False, m.span()
    return None


def extract_labels(title):
    """괄호 라벨 목록(회차 토큰 제외)."""
    labels = []
    for m in re.finditer(OPEN + r"\s*([^\[\]\(\)〈〉<>【】「」《》]{2,40}?)\s*" + CLOSE, title):
        inner = m.group(1).strip()
        if _EP_IN_BRACKET.fullmatch(m.group(0)):
            continue
        if re.fullmatch(r"\d{1,3}|[상중하上中下]|끝|Ⅰ|Ⅱ|Ⅲ|Ⅳ|Ⅴ", inner):
            continue
        labels.append((inner, m.span()))
    return labels


def series_signature(title):
    """제목 → {name, ord, epLabel, isEnd} / 시리즈 아니면 None."""
    ep = extract_episode(title)
    if not ep:
        return None
    ord_, ep_label, is_end, ep_span = ep
    labels = extract_labels(title)
    name = None
    for inner, _span in labels:
        if EXCLUDE_LABEL.match(inner) or EXCLUDE_ANY.search(inner):
            return None
        if name is None:
            name = inner
    if name is None:
        # 라벨 없음: 회차 토큰 바로 앞 텍스트를 시리즈명 후보로 (예: "AI 대전환 (상) ...")
        before = title[: ep_span[0]].strip(" -–—·:：,")
        if 4 <= len(before) <= 30 and not re.search(r"[.?!…]", before):
            name = before
        else:
            return None
    if EXCLUDE_ANY.search(title):
        return None
    return {"name": name, "ord": ord_, "epLabel": ep_label, "isEnd": is_end}


def norm_key(press, name):
    return f"{press}:{_norm(name)}"


STRONG_PLAN = re.compile(r"(기획|시리즈|특집|창간|신년|연중|르포|탐사|프로젝트|긴급점검|심층|어젠다)")


def classify(name, first_ord, has_sjh):
    """시리즈 유형: '기획' vs '연재칼럼'."""
    if has_sjh:
        return "기획"
    if STRONG_PLAN.search(name):
        return "기획"
    if PERSONAL_COLUMN.match(name):  # "우정아의 아트 스토리" 류 인명 칼럼
        return "연재칼럼"
    if first_ord > 30:
        return "연재칼럼"
    if PLAN_KEYWORDS.search(name):
        return "기획"
    if first_ord <= 5:
        return "기획"
    return "연재칼럼"
