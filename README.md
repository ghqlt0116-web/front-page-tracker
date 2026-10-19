# 조간 가판대 (front-page-tracker)

조선일보 · 중앙일보 · 동아일보 · 매일경제 · 한국경제, 그리고 토요일판 중앙SUNDAY의 **전 지면 기사**를 매일 아침 자동 수집해,

- **오늘의 1면** — 5개사 1면을 나란히 (머리기사 강조, 모의 지면 레이아웃)
- **지면 뷰** — 신문사별 A1·A2·… 면 단위 탐색 (면 내 게재 순서 = 기사 비중)
- **기획 시리즈** — 상·중·하 / 1·2·3회 연재를 자동으로 묶어 타임라인으로 추적 ("하 게재 대기중" 표시)

을 제공하는 GitHub Pages 대시보드 + 텔레그램 다이제스트입니다. 모든 기사는 `docs/data/`에 JSON으로 축적됩니다.

## 구조

```
collector/
  collect.py   # 네이버 지면보기(media.naver.com/press/{oid}/newspaper) 수집
  rules.py     # 기획 시리즈 감지 규칙 (회차 표기·시리즈명·기획/연재칼럼 분류)
  series.py    # 전체 데이터에서 시리즈 인덱스 재구축
  notify.py    # 텔레그램 다이제스트 (1면 머리기사 + 시리즈 동향, 링크 포함)
  enrich.py    # (옵션) 뉴스검색 면 번호 교차검증 — 단(段) 정보는 무의미함이 확인되어 기본 비활성
run.py         # 파이프라인 오케스트레이터
docs/          # GitHub Pages 대시보드 (index.html / app.js / style.css)
docs/data/     # papers/날짜.json, series/index.json, manifest.json, state/
.github/workflows/collect.yml  # KST 05:30 + 07:00 자동 수집
```

## 운영

- **스케줄**: 매일 KST 05:30 1차(수집+발송), 07:00 2차(보강, 신규분만 추가 발송) → 오전 8시 전 다이제스트 수신
- **백필**: Actions 탭 → collect → Run workflow → `date=YYYYMMDD`, `days=N`
- **로컬 실행**: `pip install -r requirements.txt` 후 `python run.py --days 7`
- **일요일**은 전 매체 휴간 — "기사 없음"으로 자동 스킵됩니다

## 시리즈 감지·보정

제목의 회차 표기(`(상)(중)(하)`, `〈N〉`, `[N]`, `①`, `N부/회/편/화/탄`, `·끝` 등)와 괄호 라벨로 자동 감지하고,
키워드·회차 수 기반으로 **기획 시리즈 / 연재칼럼**을 분류합니다. 오분류는 `docs/data/series/overrides.json`으로 보정:

```json
{
  "exclude": ["023:시리즈키"],
  "forceType": {"025:어떤기획": "기획"},
  "merge": {"020:옛키": "020:새키"}
}
```

## 숨김 동기화 (PC·모바일 공유)

시리즈 숨김 목록은 `docs/data/ui/hidden.json`에 저장되어 기기 간 공유됩니다.
대시보드에서 숨김/복원하면 GitHub API로 이 파일이 커밋되는데, 기기마다 토큰을 한 번 등록해야 합니다:

1. github.com → Settings → Developer settings → **Fine-grained personal access tokens** → Generate
2. Repository access: 이 저장소만 선택, Permissions: **Contents → Read and write** 만 부여
3. 대시보드 기획 시리즈 탭 → **동기화 설정** 버튼 → 토큰 붙여넣기 (기기당 1회)

토큰 없이도 숨김은 동작하지만 그 브라우저에만 저장됩니다. 요청량은 토글당 커밋 1건(시간당 한도 5,000건)으로 부하 걱정은 없습니다.

## 이관 (키 교체)

개인 식별값은 코드에 없으며, 교체 지점은 GitHub Secrets 2개뿐입니다.

1. repo **Transfer** (Settings → General → Transfer ownership) 또는 fork
2. 새 계정에서 **Settings → Pages** → Source: `Deploy from a branch`, Branch: `main` / `docs`
3. **Settings → Secrets and variables → Actions** 에 등록:
   - `TELEGRAM_BOT_TOKEN` — @BotFather 로 만든 본인 봇 토큰
   - `TELEGRAM_CHAT_ID` — 본인 채팅 ID (@userinfobot 등으로 확인)
4. Actions 탭에서 워크플로 활성화 (fork 시 1회 수동 승인 필요)
5. (선택) 숨김 동기화를 쓰려면 위 '숨김 동기화' 절차대로 본인 토큰을 기기마다 1회 등록
   — 대시보드가 Pages 주소에서 계정·저장소를 자동 인식하므로 코드 수정은 없음

## 데이터 출처·주의

네이버 뉴스 지면보기 공개 페이지에서 **제목·링크·면 번호 메타데이터만** 수집합니다 (본문 미수집).
수집 주기는 하루 2회, 신문사당 요청 1회로 원 서비스에 부하를 주지 않습니다.
