/* 조간 1면 트래커 — 바닐라 JS 대시보드 */
(() => {
  const PRESS_ORDER = ["023", "025", "020", "009", "015"];
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

  function isFront(page) {
    return /^[A-Z]?0?1$/.test(page);
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
    for (const a of doc.articles) {
      if (!isFront(a.page) || !matchQ(a.title)) continue;
      (byPress[a.press] ??= []).push(a);
    }
    let html = `<div class="front-grid">`;
    for (const oid of PRESS_ORDER) {
      const arts = (byPress[oid] || []).sort((x, y) => x.pageOrder - y.pageOrder);
      const name = state.presses[oid] || oid;
      html += `<div class="press-col"><h2 class="press-head">${esc(name)}<span class="cnt">1면 ${arts.length}건</span></h2>`;
      if (!arts.length) {
        html += `<p class="empty" style="padding:20px 0">기사 없음</p></div>`;
        continue;
      }
      const top = arts[0];
      html += `<a class="top-article" href="${top.url}" target="_blank" rel="noopener">
        ${top.thumb ? `<img src="${top.thumb}" alt="" loading="lazy" onerror="this.remove()">` : ""}
        <div class="kicker">머리기사 ${badges(top)}</div>
        <h3 class="headline">${esc(top.title)}</h3></a>`;
      html += `<ul class="sub-list">`;
      for (const a of arts.slice(1)) {
        html += `<li><a href="${a.url}" target="_blank" rel="noopener">${badges(a)}${esc(a.title)}</a></li>`;
      }
      html += `</ul></div>`;
    }
    html += `</div>`;
    el.innerHTML = html;
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
    for (const p of pages) {
      const list = byPage.get(p).sort((x, y) => x.pageOrder - y.pageOrder);
      const open = isFront(p) ? " open" : "";
      html += `<details class="page-sec"${open}><summary><span class="pageno">${esc(p)}면</span><span class="preview">${esc(list[0].title)}</span><span class="cnt" style="font-family:var(--sans);font-size:12px;color:var(--ink-soft)">${list.length}건</span></summary><ul class="page-arts">`;
      list.forEach((a, i) => {
        html += `<li>${i === 0 ? '<span class="badge top">톱</span>' : ""}${badges(a)}<a href="${a.url}" target="_blank" rel="noopener">${esc(a.title)}</a></li>`;
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
