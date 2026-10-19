/* 조간 1면 트래커 — 바닐라 JS 대시보드 */
(() => {
  const PRESS_ORDER = ["023", "025", "353", "020", "009", "015"];
  const state = {
    view: "front",
    date: null,
    dates: [],
    presses: {},
    press: "023", // 지면 뷰 선택
    typeFilter: "기획",
    statusFilter: "all",
    q: "",
    paperCache: {},
    seriesIndex: null,
  };

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  async function fetchJSON(path) {
    const r = await fetch(path, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }

  async function loadPaper(date) {
    if (!state.paperCache[date]) {
      state.paperCache[date] = await fetchJSON(`data/papers/${date}.json`);
    }
    return state.paperCache[date];
  }

  async function loadSeries() {
    if (!state.seriesIndex) {
      try {
        state.seriesIndex = (await fetchJSON("data/series/index.json")).series;
      } catch {
        state.seriesIndex = [];
      }
    }
    return state.seriesIndex;
  }

  function pageParts(page) {
    const m = page.match(/^([A-Za-z]*)0*(\d+)$/);
    return m ? { sec: m[1].toUpperCase(), num: +m[2] } : { sec: "Z", num: 999 };
  }

  // 매체별 '종합 1면' 섹션: A섹션이 있으면 A, 없으면(중앙SUNDAY=T 등) 가장 앞 섹션
  function mainFrontSec(articles) {
    const secs = new Set(
      articles.filter((a) => pageParts(a.page).num === 1).map((a) => pageParts(a.page).sec)
    );
    if (!secs.size) return null;
    if (secs.has("A") || secs.has("")) return secs.has("A") ? "A" : "";
    return [...secs].sort()[0];
  }

  // 특집·협찬성 섹션 추정 (제목 묶음에 특집 키워드가 보이면 태그만 달고 표시는 유지)
  const SPECIAL_RE = /(특집|창간|기념|주년|포럼|콘퍼런스|컨퍼런스|어워드|시상|수상|상생|공헌|캠페인|박람회|엑스포)/;

  // 관련 지면 기사 추정: 같은 신문·같은 날 안쪽 면에서 제목 핵심 단어가 겹치는 기사
  const STOPWORDS = new Set([
    "단독", "속보", "종합", "오늘", "내일", "올해", "한국", "정부", "대통령", "국내",
    "사진", "포토", "전망", "논란", "확대", "강화", "추진", "발표", "그래픽",
  ]);
  function tokenize(title) {
    return title
      .replace(/[\[\]()〈〉<>【】「」《》'"'"…·]/g, " ")
      .split(/[^0-9A-Za-z가-힣]+/)
      .filter((t) => t.length >= 2 && !STOPWORDS.has(t));
  }
  // 사설·칼럼류: 매칭은 하되 라벨을 달아 구분 (1면 이슈가 사설까지 이어졌다는 신호)
  const OPINION_RE =
    /^\s*[\[(〈<]?\s*(사설|시론|칼럼|기고|특별기고|만물상|횡설수설|분수대|천자칼럼|매경포럼|데스크에서|기자24시|취재수첩|기자수첩|오늘과 내일|광화문에서)/;
  // 비뉴스성(사진·만평·부음 등)은 관련기사 후보에서 제외
  const NONNEWS_RE = /^\s*[\[(〈<]?\s*(사진|포토|만평|만화|알림|알립니다|부음|부고|인사)\s*[\])〉>]/;

  function findRelated(art, pool) {
    const tk = new Set(tokenize(art.title));
    if (!tk.size) return [];
    const scored = [];
    for (const a of pool) {
      if (a.articleId === art.articleId || NONNEWS_RE.test(a.title)) continue;
      const shared = tokenize(a.title).filter((t) => tk.has(t));
      const uniq = [...new Set(shared)];
      const strong = uniq.some((t) => t.length >= 5);
      if (uniq.length >= 2 || (uniq.length === 1 && strong)) {
        scored.push([uniq.length + (strong ? 1 : 0), a]);
      }
    }
    return scored.sort((x, y) => y[0] - x[0]).slice(0, 2).map(([, a]) => a);
  }

  function relatedHtml(art, pool) {
    // 수집기가 본문 기반으로 계산한 related가 있으면 우선, 없으면 제목 기반 추정
    const rel = Array.isArray(art.related) ? art.related.slice(0, 3) : findRelated(art, pool);
    if (!rel.length) return "";
    return `<div class="related">${rel
      .map((r) => {
        const op = OPINION_RE.exec(r.title);
        const tag = op ? `<span class="rel-op">${esc(op[1])}</span>` : "";
        // 라벨로 표시하므로 제목 선두의 [사설] 등 코너명은 중복 제거
        const shown = op ? r.title.replace(/^\s*[\[(〈<]\s*[^\])〉>]{1,14}\s*[\])〉>]\s*/, "") : r.title;
        return `<a href="${r.url}" target="_blank" rel="noopener"${op ? ' class="op"' : ""}>↳ <span class="rel-page">${esc(r.page)}면</span> ${tag}${esc(shown)}</a>`;
      })
      .join("")}</div>`;
  }

  function matchQ(title) {
    return !state.q || title.toLowerCase().includes(state.q.toLowerCase());
  }

  function badges(a) {
    let h = "";
    if (a.seriesKey) {
      const label = a.seriesType === "기획" ? "기획" : "연재";
      h += `<span class="badge series">${label}</span>`;
    }
    // 지면보기 미등록 → 뉴스검색 지면 배지로 보강된 기사 (게재 순서 미상)
    if (a.source === "search") h += `<span class="badge search" title="지면보기에 없어 뉴스검색으로 찾은 지면 기사">검색보강</span>`;
    return h;
  }

  /* ── 오늘의 1면 ── */
  async function renderFront() {
    const el = $("#view-front");
    let doc;
    try {
      doc = await loadPaper(state.date);
    } catch {
      el.innerHTML = `<p class="empty">이 날짜의 데이터가 없습니다 (휴간일이거나 아직 수집 전).</p>`;
      return;
    }
    const byPress = {};
    for (const a of doc.articles) (byPress[a.press] ??= []).push(a);

    let html = `<div class="front-grid">`;
    for (const oid of PRESS_ORDER) {
      const all = byPress[oid] || [];
      if (!all.length) continue; // 미발행(휴간·주말전용지 평일 등)은 컬럼 자체를 숨김
      const mainSec = mainFrontSec(all);
      const fronts = all
        .filter((a) => {
          const p = pageParts(a.page);
          return p.num === 1 && p.sec === mainSec && matchQ(a.title);
        })
        .sort((x, y) => x.pageOrder - y.pageOrder);
      // 안쪽 면 전체: 관련 기사 추정 풀
      const inner = all.filter((a) => !(pageParts(a.page).num === 1 && pageParts(a.page).sec === mainSec));
      const name = state.presses[oid] || oid;
      html += `<div class="press-col"><h2 class="press-head">${esc(name)}<span class="cnt">1면 ${fronts.length}건</span></h2>`;
      if (!fronts.length) {
        html += `<p class="empty" style="padding:20px 0">기사 없음</p></div>`;
        continue;
      }
      const top = fronts[0];
      html += `<a class="top-article" href="${top.url}" target="_blank" rel="noopener">
        ${top.thumb ? `<img src="${top.thumb}" alt="" loading="lazy" onerror="this.remove()">` : ""}
        <div class="kicker">머리기사 ${badges(top)}</div>
        <h3 class="headline">${esc(top.title)}</h3></a>`;
      html += relatedHtml(top, inner);
      html += `<ul class="sub-list">`;
      for (const a of fronts.slice(1)) {
        html += `<li><a href="${a.url}" target="_blank" rel="noopener">${badges(a)}${esc(a.title)}</a>${relatedHtml(a, inner)}</li>`;
      }
      html += `</ul>`;

      // 별지 섹션 1면 (B1 경제, E1 등): 면 단위로 전체 기사 표시
      const sectPages = new Map();
      for (const a of all) {
        const p = pageParts(a.page);
        if (p.num === 1 && p.sec !== mainSec && matchQ(a.title)) {
          if (!sectPages.has(a.page)) sectPages.set(a.page, []);
          sectPages.get(a.page).push(a);
        }
      }
      if (sectPages.size) {
        html += `<div class="sect-fronts"><div class="sect-head">섹션 1면</div>`;
        for (const pg of [...sectPages.keys()].sort()) {
          const list = sectPages.get(pg).sort((x, y) => x.pageOrder - y.pageOrder);
          const special = SPECIAL_RE.test(list.map((a) => a.title).join(" "));
          html += `<div class="sect-group${special ? " special" : ""}">
            <span class="badge">${esc(pg)}면</span>${special ? `<span class="badge special-tag">특집 추정</span>` : ""}
            <ul class="sub-list">`;
          for (const a of list) {
            html += `<li><a href="${a.url}" target="_blank" rel="noopener">${badges(a)}${esc(a.title)}</a></li>`;
          }
          html += `</ul></div>`;
        }
        html += `</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
    el.innerHTML = html || `<p class="empty">기사 없음</p>`;
  }

  /* ── 지면 뷰 ── */
  async function renderPages() {
    const el = $("#view-pages");
    let doc;
    try {
      doc = await loadPaper(state.date);
    } catch {
      el.innerHTML = `<p class="empty">이 날짜의 데이터가 없습니다.</p>`;
      return;
    }
    let html = `<div class="press-tabs">`;
    for (const oid of PRESS_ORDER) {
      html += `<button data-press="${oid}" class="${oid === state.press ? "active" : ""}">${esc(state.presses[oid] || oid)}</button>`;
    }
    html += `</div>`;

    const arts = doc.articles.filter((a) => a.press === state.press && matchQ(a.title));
    const byPage = new Map();
    for (const a of arts) {
      if (!byPage.has(a.page)) byPage.set(a.page, []);
      byPage.get(a.page).push(a);
    }
    const pageKey = (p) => {
      const m = p.match(/^([A-Za-z]*)(\d+)$/);
      return m ? [m[1] || "A", parseInt(m[2], 10)] : ["Z", 999];
    };
    const pages = [...byPage.keys()].sort((a, b) => {
      const [sa, na] = pageKey(a), [sb, nb] = pageKey(b);
      return sa === sb ? na - nb : sa < sb ? -1 : 1;
    });
    if (!pages.length) {
      el.innerHTML = html + `<p class="empty">기사 없음</p>`;
      bindPressTabs(el);
      return;
    }
    const mainSec = mainFrontSec(arts);
    for (const p of pages) {
      const list = byPage.get(p).sort((x, y) => x.pageOrder - y.pageOrder);
      const pp = pageParts(p);
      const open = pp.num === 1 && pp.sec === mainSec ? " open" : "";
      html += `<details class="page-sec"${open}><summary><span class="pageno">${esc(p)}면</span><span class="preview">${esc(list[0].title)}</span><span class="cnt" style="font-family:var(--sans);font-size:12px;color:var(--ink-soft)">${list.length}건</span></summary><ul class="page-arts">`;
      list.forEach((a, i) => {
        // 검색 보강 기사는 게재 순서를 모르므로 '톱' 라벨을 달지 않음
        html += `<li>${i === 0 && a.source !== "search" ? '<span class="badge top">톱</span>' : ""}${badges(a)}<a href="${a.url}" target="_blank" rel="noopener">${esc(a.title)}</a></li>`;
      });
      html += `</ul></details>`;
    }
    el.innerHTML = html;
    bindPressTabs(el);
  }

  function bindPressTabs(el) {
    $$(".press-tabs button", el).forEach((b) =>
      b.addEventListener("click", () => {
        state.press = b.dataset.press;
        renderPages();
      })
    );
  }

  /* ── 기획 시리즈 뷰 ── */
  const SJH_FULL = ["상", "중", "하"];
  function pendingEpisodes(rec) {
    // 상·중·하 시리즈: 아직 안 나온 회차를 '대기'로 표시
    const labels = rec.episodes.map((e) => e.label);
    if (!labels.some((l) => SJH_FULL.includes(l))) return [];
    if (rec.status === "completed") return [];
    return SJH_FULL.filter((l) => !labels.includes(l));
  }

  async function renderSeries() {
    const el = $("#view-series");
    const idx = await loadSeries();
    let html = `<div class="chips">
      <button data-f="type:기획" class="${state.typeFilter === "기획" ? "active" : ""}">기획 시리즈</button>
      <button data-f="type:연재칼럼" class="${state.typeFilter === "연재칼럼" ? "active" : ""}">연재칼럼</button>
      <button data-f="type:all" class="${state.typeFilter === "all" ? "active" : ""}">전체</button>
      <span style="width:12px"></span>
      <button data-f="st:all" class="${state.statusFilter === "all" ? "active" : ""}">전체 상태</button>
      <button data-f="st:ongoing" class="${state.statusFilter === "ongoing" ? "active" : ""}">진행중</button>
      <button data-f="st:completed" class="${state.statusFilter === "completed" ? "active" : ""}">완결</button>
    </div>`;

    const rows = idx.filter(
      (r) =>
        (state.typeFilter === "all" || r.seriesType === state.typeFilter) &&
        (state.statusFilter === "all" || r.status === state.statusFilter) &&
        (!state.q ||
          r.name.toLowerCase().includes(state.q.toLowerCase()) ||
          r.episodes.some((e) => matchQ(e.title)))
    );
    if (!rows.length) {
      html += `<p class="empty">조건에 맞는 시리즈가 없습니다.${
        state.typeFilter === "기획"
          ? "<br>기획 시리즈(상·중·하, 1·2·3회)는 게재 시점에 자동 감지됩니다 — 연재칼럼 탭도 확인해보세요."
          : ""
      }</p>`;
      el.innerHTML = html;
      bindChips(el);
      return;
    }
    html += `<div class="series-grid">`;
    for (const r of rows) {
      const stat =
        r.status === "completed"
          ? `완결`
          : `<span class="status-ongoing">진행중</span>`;
      html += `<div class="series-card"><h3>[${esc(r.name)}]</h3>
        <div class="series-meta">${esc(r.pressName)} · ${esc(r.seriesType)} · ${stat} · ${r.episodes.length}회 게재 · ${r.firstDate} ~ ${r.lastDate}</div>
        <ul class="ep-timeline">`;
      for (const e of r.episodes) {
        html += `<li><span class="ep-label">(${esc(e.label)})</span><a href="${e.url}" target="_blank" rel="noopener">${esc(e.title)}</a><span class="ep-meta">${e.date} · ${esc(e.page)}면</span></li>`;
      }
      for (const l of pendingEpisodes(r)) {
        html += `<li class="pending"><span class="ep-label">(${l})</span>게재 대기</li>`;
      }
      html += `</ul></div>`;
    }
    html += `</div>`;
    el.innerHTML = html;
    bindChips(el);
  }

  function bindChips(el) {
    $$(".chips button", el).forEach((b) =>
      b.addEventListener("click", () => {
        const [k, v] = b.dataset.f.split(":");
        if (k === "type") state.typeFilter = v;
        else state.statusFilter = v;
        renderSeries();
      })
    );
  }

  /* ── 공통 ── */
  function render() {
    $$(".view").forEach((v) => (v.hidden = true));
    $(`#view-${state.view}`).hidden = false;
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === state.view));
    $("#dateNav").style.visibility = state.view === "series" ? "hidden" : "visible";
    if (state.view === "front") renderFront();
    else if (state.view === "pages") renderPages();
    else renderSeries();
  }

  function setDate(d) {
    state.date = d;
    const i = state.dates.indexOf(d);
    $("#dateSelect").value = d;
    $("#prevDay").disabled = i <= 0;
    $("#nextDay").disabled = i >= state.dates.length - 1;
    render();
  }

  async function init() {
    const manifest = await fetchJSON("data/manifest.json");
    state.dates = manifest.dates;
    state.presses = Object.fromEntries(
      Object.entries(manifest.presses).map(([k, v]) => [k, v])
    );
    const sel = $("#dateSelect");
    sel.innerHTML = state.dates
      .map((d) => `<option value="${d}">${d}</option>`)
      .join("");
    sel.addEventListener("change", () => setDate(sel.value));
    $("#prevDay").addEventListener("click", () => {
      const i = state.dates.indexOf(state.date);
      if (i > 0) setDate(state.dates[i - 1]);
    });
    $("#nextDay").addEventListener("click", () => {
      const i = state.dates.indexOf(state.date);
      if (i < state.dates.length - 1) setDate(state.dates[i + 1]);
    });
    $$(".tab").forEach((t) =>
      t.addEventListener("click", () => {
        state.view = t.dataset.view;
        render();
      })
    );
    let deb;
    $("#search").addEventListener("input", (e) => {
      clearTimeout(deb);
      deb = setTimeout(() => {
        state.q = e.target.value.trim();
        render();
      }, 200);
    });
    setDate(state.dates[state.dates.length - 1]);
  }

  init().catch((e) => {
    $("#app").innerHTML = `<p class="empty">데이터 로드 실패: ${esc(String(e))}</p>`;
  });
})();
