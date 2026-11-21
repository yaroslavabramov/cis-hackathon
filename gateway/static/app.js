const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const aed = (n) => "AED " + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const short = (n) => "AED " + Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
let S = null, clockBase = 0, clockAt = 0, seen = new Set(), selected = null, lastAuto = null;
const shown = { real: null, attacker: null };

function tickClock() {
  if (!clockBase) return;
  const d = new Date(clockBase + (performance.now() - clockAt));
  $("#clock").textContent = d.toTimeString().slice(0, 8);
}
setInterval(tickClock, 200);

function tween(key, el, target) {
  const from = shown[key] ?? target;
  shown[key] = target;
  if (from === target) { el.textContent = aed(target); return; }
  const t0 = performance.now(), dur = 700;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = aed(from + (target - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function scoreClass(s) { return s >= S.threshold ? "high" : s >= 30 ? "mid" : ""; }

function renderFeed() {
  const rows = S.events.slice().reverse().map((e) => {
    const key = `${e.ts}|${e.kind}|${e.text}|${e.sid}|${e.status ?? ""}`;
    const fresh = !seen.has(key); seen.add(key);
    if (e.kind === "request") {
      const tag = e.target === "shadow" ? `<span class="tag shadow">MIRAGE</span>` : `<span class="tag real">REAL</span>`;
      const st = e.status >= 400 ? `<span class="tag bad">${e.status}</span>` : "";
      return `<div class="row" ${fresh ? "" : 'style="animation:none"'}><span class="t">${esc(e.ts)}</span>
        <span class="what"><span class="who">${esc((e.customer || "").split(" ")[0])}</span> · <span class="path">${esc(e.text)}</span></span>
        <span>${st} ${tag} <span class="score ${scoreClass(e.score)}">${e.score}</span></span></div>`;
    }
    const cls = { diverted: "diverted", alert: "alert", devin: "devin", release: "release", fraud: "alert", protect: "protect" }[e.kind] || "sys";
    return `<div class="row ${cls}" ${fresh ? "" : 'style="animation:none"'}><span class="t">${esc(e.ts)}</span>
      <span class="what">${e.customer ? esc(e.customer) + " · " : ""}${esc(e.text)}</span><span></span></div>`;
  });
  $("#feed").innerHTML = rows.join("");
  $("#stats").textContent = `${S.stats.sessions} sessions · ${S.stats.requests} requests`;
}

function renderTop() {
  const sh = S.shadow;
  $("#shadow").innerHTML = `<span class="dot ${esc(sh.status)}"></span>Shadow bank · ${esc(sh.label)} <span class="mono">${esc(sh.kind === "daytona" ? sh.detail : "")}</span>`;
  $("#shadow").title = sh.detail;
  $("#protection").checked = S.protection;
}

function flowSvg(inc) {
  const d = inc.destinations;
  if (!d.length) return `<div class="muted">No outbound transfers yet.</div>`;
  const rowH = 46, h = Math.max(120, d.length * rowH), W = 600, X = 250, max = Math.max(...d.map((x) => x.total));
  const vy = h / 2, color = inc.diverted ? "var(--mirage)" : "var(--red)";
  const cut = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
  const links = d.map((x, i) => {
    const y = i * rowH + 20, w = 2 + 10 * (x.total / max);
    return `<path d="M140 ${vy} C 200 ${vy}, 190 ${y}, ${X} ${y}" stroke="${color}" stroke-opacity=".55" stroke-width="${w}" fill="none"/>`;
  }).join("");
  const nodes = d.map((x, i) => {
    const y = i * rowH;
    const ref = x.phone ? `☎ ${x.phone}` : x.reference && x.reference.startsWith("USDT") ? x.reference : x.iban;
    return `<g class="node"><rect x="${X}" y="${y}" width="${W - X - 2}" height="40" rx="9"/>
      <text x="${X + 12}" y="${y + 16}">${esc(cut(x.name, 30))}</text>
      <text class="m ${x.phone ? "ph" : ""}" x="${X + 12}" y="${y + 32}">${esc(x.country)} · ${esc(cut(ref, 36))}</text>
      <text class="a" x="${W - 14}" y="${y + 16}" text-anchor="end">${short(x.total)}</text>
      <text class="m" x="${W - 14}" y="${y + 32}" text-anchor="end">${x.count} transfer${x.count > 1 ? "s" : ""}</text></g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${h}">${links}
    <g class="node"><rect x="0" y="${vy - 28}" width="140" height="56" rx="12"/>
    <text x="12" y="${vy - 5}">${esc(inc.name.split(" ")[0])}'s account</text>
    <text class="m" x="12" y="${vy + 13}">${esc(inc.customer_id)}</text></g>${nodes}</svg>`;
}

function devinPanel(inc) {
  const dv = inc.devin;
  const prs = dv?.prs || [];
  const st = dv?.status;
  const steps = [
    ["Attack log captured by Mirage", !!inc.log.length, false],
    ["Devin session started", !!dv?.url, dv && !dv.url && st !== "error"],
    ["Root cause & fix in progress", prs.length > 0, !!dv?.url && !prs.length && !["exit", "error"].includes(st)],
    ["Pull request with regression test", prs.length > 0, false],
  ];
  const body = steps.map(([t, done, live]) => `<div class="step ${done ? "done" : live ? "live" : ""}"><span class="b"></span>${t}</div>`).join("");
  const links = (dv?.url ? `<div class="muted" style="margin-top:10px">Session: <a href="${esc(dv.url)}" target="_blank">${esc(dv.url)}</a></div>` : "") +
    prs.map((p) => `<div class="pr">PR · <a href="${esc(p)}" target="_blank">${esc(p)}</a></div>`).join("") +
    (S.devin_reference && !prs.length ? `<div class="muted" style="margin-top:10px">Earlier run on the same attack: <a href="${esc(S.devin_reference)}" target="_blank">${esc(S.devin_reference.replace("https://github.com/", ""))}</a></div>` : "") +
    (st === "error" ? `<div class="muted" style="color:var(--red);margin-top:8px">${esc(dv.detail || "error")}</div>` : "");
  const btn = !dv ? `<button id="devin-btn" style="margin-top:12px" ${S.devin_configured ? "" : "disabled title='Set DEVIN_API_KEY and DEVIN_ORG_ID'"}>Send attack log to Devin</button>` : "";
  return `<div class="panel"><div class="panel-h"><h2>Devin · find and fix the hole</h2><span class="muted">${esc(st || "")}</span></div>
    <div class="steps">${body}</div>${links}${btn}</div>`;
}

function pickIncident() {
  const list = S.incidents || [];
  if (S.incident && S.incident.id !== lastAuto) { selected = lastAuto = S.incident.id; }
  return list.find((i) => i.id === selected) || S.incident;
}

function chipsHtml(current) {
  const list = S.incidents || [];
  if (list.length < 2) return "";
  const label = (i) => i.kind === "victim" ? "victim protected" : i.diverted ? "attacker trapped" : "protection off";
  return `<div class="chips">${list.map((i) => `<button class="chip ${i.kind} ${i.id === current.id ? "active" : ""}" data-id="${esc(i.id)}">
    <b>${esc(i.name.split(" ")[0])}</b> · ${label(i)} <span class="mono">${esc(i.id)}</span></button>`).join("")}</div>`;
}

function watchlistHtml(highlight) {
  const rows = (S.mules || []).map((m) => `<tr class="${m.iban === highlight ? "hit" : ""}"><td>${esc(m.name)}</td><td class="mono muted">${esc(m.country)} · ${esc(m.iban.slice(0, 10))}…</td>
    <td class="mono muted">${esc(m.incident)} · ${esc(m.first_seen)}</td><td class="mono num">${short(m.total)}</td><td class="mono num">${m.hits ? `<b>${m.hits} blocked</b>` : "–"}</td></tr>`).join("");
  return `<div class="panel"><div class="panel-h"><h2>Mule watchlist</h2><span class="muted">${(S.mules || []).length} accounts learned from trapped attackers</span></div>
    <table class="watch"><tr><th>Account</th><th>IBAN</th><th>Learned in</th><th>Fake money sent</th><th>Victims protected</th></tr>${rows}</table></div>`;
}

function renderVictim(inc, stage) {
  const first = inc.name.split(" ")[0], m = inc.mule || {}, held = inc.held[inc.held.length - 1] || {};
  const released = inc.status === "released", fraud = inc.status === "confirmed_fraud";
  const without = inc.signals.filter((g) => g.key !== "known_mule").reduce((a, g) => a + g.weight, 0);
  const sigs = inc.signals.map((g) => `<div class="sig"><span class="w">+${g.weight}</span><div><b>${esc(g.title)}</b><div>${esc(g.detail)}</div></div></div>`).join("");
  stage.innerHTML = chipsHtml(inc) + `
    <div class="banner protected ${released ? "released" : ""}">
      <div><div class="state">${released ? "RELEASED AFTER CUSTOMER CONFIRMATION" : fraud ? "SCAM CONFIRMED · TRANSFER VOIDED" : "SCAM VICTIM PROTECTED"}</div>
        <div class="title">${esc(first)} was about to send ${short(held.amount)} to ${esc(m.name)}. That account received stolen money ${esc(m.first_seen)} tonight, so the transfer is held and ${esc(first)} was warned.</div>
        <div class="meta"><span>Session <b class="mono">${esc(inc.id)}</b></span><span>${esc(inc.name)}</span>
        <span>own device <b class="mono">${esc(inc.device_id)}</b></span><span>FaceID ✓ step-up ✓</span><span>held ${esc(inc.protected_at)}</span></div></div>
      <div class="gauge" style="--v:${inc.score};--c:var(--amber)"><span>${inc.score}</span><small>RISK</small></div>
    </div>
    <div class="balances">
      <div class="bal real"><div class="lbl">${esc(first)}'s real balance</div><div class="amt" id="amt-real"></div>
        <div class="note">${released ? "transfer released after confirmation" : `${short(held.amount)} held, not sent`}</div></div>
      <div class="bal warn"><div class="lbl">What ${esc(first)} sees in his app</div>
        <div class="warnmsg"><b>Transfer paused for your safety.</b> The receiving account was used tonight to receive stolen money. Desert Bank will never ask you to move money to a "safe account". If someone is on the phone with you, hang up.</div></div>
    </div>
    <div class="grid2">
      <div class="panel"><div class="panel-h"><h2>Why this transfer was held</h2><span class="muted">threshold ${S.threshold}</span></div>
        <div class="signals">${sigs}</div>
        <div class="callout">Without the watchlist this transfer scores <b>${without}/100</b>. It is his own phone, his own FaceID, his own step-up: it would have gone through.</div></div>
      <div class="panel"><div class="panel-h"><h2>How Mirage knew</h2><span class="muted">deceive attackers · protect victims</span></div>
        <div class="mulecard"><div class="mono">${esc(m.name)} · ${esc(m.country)}</div><div class="muted mono">${esc(m.iban)}</div>
        <p>At <b>${esc(m.first_seen)}</b>, the attacker trapped in incident <b class="mono">${esc(m.incident)}</b> sent ${short(m.total)} of <b>fake</b> money from ${esc(m.victim)}'s shadow account to this IBAN.
        Mirage added it to the watchlist. Minutes later the same scam network called ${esc(first)}.</p>
        <p class="muted">We don't deceive ${esc(first)}: he is the real customer. He gets an honest warning instead.</p></div></div>
    </div>
    <div class="bottom">${watchlistHtml(m.iban)}
      <div class="panel"><div class="panel-h"><h2>Decision</h2><a href="/api/incidents/${esc(inc.id)}/report" target="_blank">Incident report ↓</a></div>
        <div class="actions">
          <button class="ok" id="release" ${!released && !fraud ? "" : "disabled"}><b>Customer insists: release</b><span>Send the held transfer after a call with ${esc(first)}</span></button>
          <button class="bad" id="fraud" ${!released && !fraud ? "" : "disabled"}><b>Confirm scam: void</b><span>Cancel the transfer, add the case to the mule's file</span></button>
        </div></div>
    </div>`;
  if (shown.realStart == null) shown.realStart = inc.balances.real;
  shown.real = null;
  $("#amt-real").textContent = aed(inc.balances.real);
}

function tacticsHtml(inc) {
  const t = inc.tactics || {}, d = inc.deception || {};
  const card = (key, title, idle, done) => {
    const n = (t[key] || []).length;
    return `<div class="tactic ${n ? "on" : ""}"><div class="th"><b>${title}</b><span>${n ? `${n}×` : "armed"}</span></div>
      <div class="td">${n ? done : idle}</div></div>`;
  };
  const probe = d.probe_to ? `${esc(d.probe_to.name)} · ${esc(d.probe_to.iban.slice(0, 8))}…` : "";
  return `<div class="tactics">
    ${card("probe", "Probe pass-through", "Tiny test transfers really go out, so the attacker's check succeeds.",
      `AED ${Number(d.real_lost || 0).toLocaleString()} really sent to <b>${probe}</b>: the attacker's own account.`)}
    ${card("sticky", "Sticky mirage", "Re-logins from the same device or IP land in the same fake bank.",
      `${d.relogins} re-login${d.relogins === 1 ? "" : "s"} from a fresh session: still inside the mirage, balances consistent.`)}
    ${card("bait", "Bait account", "A fake savings account appears once the real one is 'empty'.",
      `Fake "Savings Plus" ${short(1200000)} chased into ${(t.bait || []).length} transfers to new mules.`)}
    ${card("friction", "Compliance friction", "Big wires ask for the beneficiary's phone and purpose.",
      `${d.phones} mule phone number${d.phones === 1 ? "" : "s"} handed over by the attacker.`)}
  </div>`;
}

function metricsHtml(inc) {
  const d = inc.deception || {};
  const m = Math.floor((d.engaged_s || 0) / 60), sec = (d.engaged_s || 0) % 60;
  const cell = (v, l, cls = "") => `<div class="metric ${cls}"><b>${v}</b><span>${l}</span></div>`;
  return `<div class="metrics">${cell(`${m}:${String(sec).padStart(2, "0")}`, "in the mirage")}
    ${cell(short(d.fake_stolen), "fake money stolen", "fake")}${cell(short(d.real_lost), "real money lost", "real")}
    ${cell(d.mules || 0, "mule accounts")}${cell(d.phones || 0, "phone numbers")}</div>`;
}

function renderStage() {
  const stage = $("#stage"), inc = pickIncident();
  if (!inc) {
    shown.real = shown.attacker = shown.realStart = null;
    const rows = (S.accounts || []).map((a) => `<tr><td>${esc(a.name)}</td><td class="mono muted">${esc(a.account)}</td>
      <td class="mono num">${aed(a.balance)}</td></tr>`).join("");
    stage.innerHTML = `<div class="idle">
      <div class="big">Desert Bank · night shift</div>
      <div class="prot ${S.protection ? "on" : "off"}">Mirage protection is ${S.protection ? "ON" : "OFF"}</div>
      <div class="panel accounts"><div class="panel-h"><h2>Customer accounts (real balances)</h2><span class="muted">${S.stats.requests} requests seen</span></div>
        <table>${rows}</table></div>
      <div class="how">
        <div><b>1</b>Every request to the bank passes through Mirage and gets a risk score.</div>
        <div><b>2</b>If a session looks like an attack (risk ${S.threshold}+), it is not blocked.</div>
        <div><b>3</b>Instead, it is silently moved into a fake copy of the bank. The attacker keeps "stealing" fake money.</div>
      </div></div>`;
    return;
  }
  if (inc.kind === "victim") {
    renderVictim(inc, stage);
    bindActions(inc);
    return;
  }
  const off = !inc.diverted, released = inc.status === "released", fraud = inc.status === "confirmed_fraud";
  const sent = inc.balances.real < (shown.realStart ?? inc.balances.real);
  const state = released ? "RELEASED AFTER CUSTOMER CONFIRMATION" : fraud ? "FRAUD CONFIRMED · REPORT FILED" :
    off ? "ATTACK IN PROGRESS · PROTECTION OFF" : "ATTACKER TRAPPED IN A FAKE BANK";
  const first = inc.name.split(" ")[0];
  const title = off ? `Protection is off: the attacker is moving ${first}'s real money out of the bank` :
    released ? "Held transfers posted to the real account" :
    `The attacker was moved into a fake copy of the bank. He thinks he is stealing; ${first}'s real money hasn't moved.`;
  const drained = off && inc.balances.real < 1;
  const realNote = released ? "held transfers posted after the customer confirmed" : off ? (drained ? "drained: the money really left the bank" : "real money is leaving the bank") : "in the real bank database · only the AED 1 test transfer left, on purpose";
  const fakeNote = inc.diverted ? `fake balances in the shadow copy · ${inc.held.length} transfers "approved", only the AED 1 probe was real` : "no deception: he sees the real balance";
  const sigs = inc.signals.map((s) => `<div class="sig" title="${esc(s.detail)}"><span class="w">+${s.weight}</span><div><b>${esc(s.title)}</b><div>${esc(s.detail)}</div></div></div>`).join("");
  const eps = inc.endpoints.map((e) => `<span class="${e.includes("/v1/transfers") ? "hot" : ""}">${esc(e)}</span>`).join("");

  stage.innerHTML = chipsHtml(inc) + `
    <div class="banner ${off ? "off" : ""} ${released ? "released" : ""}">
      <div><div class="state">${state}</div><div class="title">${title}</div>
        <div class="meta"><span>Session <b class="mono">${esc(inc.id)}</b></span><span>${esc(inc.name)}</span>
        <span>device <b class="mono">${esc(inc.device_id)}</b></span><span>IP <b class="mono">${esc(inc.ip)}</b></span>
        <span>login ${esc(inc.started)}</span><span>risk <b>${inc.score}</b></span>
        ${inc.diverted_at ? `<span>diverted <b>${esc(inc.diverted_at)}</b></span>` : ""}</div></div>
      ${inc.diverted ? metricsHtml(inc) : `<div class="gauge" style="--v:${inc.score};--c:var(--red)"><span>${inc.score}</span><small>RISK</small></div>`}
    </div>
    <div class="balances">
      <div class="bal real ${drained || (off && sent) ? "drained" : ""}"><div class="lbl">${esc(first)}'s real balance</div><div class="amt" id="amt-real"></div><div class="note">${realNote}</div></div>
      <div class="bal fake"><div class="lbl">What the attacker sees on his screen (all accounts)</div><div class="amt" id="amt-fake"></div><div class="note">${fakeNote}</div></div>
    </div>
    ${inc.diverted ? tacticsHtml(inc) : ""}
    <div class="grid2">
      <div class="panel"><div class="panel-h"><h2>Why this session was flagged</h2><span class="muted">threshold ${S.threshold}</span></div>
        <div class="meter"><i style="width:${inc.score}%"></i><em style="left:${S.threshold}%"></em></div>
        <div class="signals compact">${sigs}</div></div>
      <div class="panel flow"><div class="panel-h"><h2>Where the attacker tried to send the money</h2><span class="muted">${inc.destinations.length} mule accounts revealed</span></div>
        ${flowSvg(inc)}<div class="endpoints">${eps}</div></div>
    </div>
    <div class="bottom">${devinPanel(inc)}
      <div class="panel"><div class="panel-h"><h2>Morning decision</h2><a href="/api/incidents/${esc(inc.id)}/report" target="_blank">Incident report ↓</a></div>
        <div class="actions">
          <button class="ok" id="release" ${inc.diverted && !released && !fraud ? "" : "disabled"}><b>It was the customer: release</b><span>Post the ${inc.held.length} held transfers to the real ledger</span></button>
          <button class="bad" id="fraud" ${inc.diverted && !released && !fraud ? "" : "disabled"}><b>Confirm fraud: void & report</b><span>Void held transfers, report ${inc.destinations.length} destination accounts</span></button>
        </div></div>
    </div>`;
  if (shown.realStart == null) shown.realStart = inc.balances.real;
  tween("real", $("#amt-real"), inc.balances.real);
  tween("attacker", $("#amt-fake"), inc.balances.attacker);
  bindActions(inc);
}

function bindActions(inc) {
  const post = (url) => fetch(url, { method: "POST" });
  $("#release")?.addEventListener("click", () => post(`/api/incidents/${inc.id}/release`));
  $("#fraud")?.addEventListener("click", () => post(`/api/incidents/${inc.id}/fraud`));
  $("#devin-btn")?.addEventListener("click", () => post(`/api/incidents/${inc.id}/devin`));
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => { selected = c.dataset.id; shown.real = shown.attacker = shown.realStart = null; renderStage(); }));
}

function render() {
  clockBase = Date.parse(S.clock); clockAt = performance.now(); tickClock();
  renderTop(); renderFeed(); renderStage();
}

$("#protection").addEventListener("change", (e) =>
  fetch("/api/protection", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: e.target.checked }) }));
$("#reset").addEventListener("click", () => { seen = new Set(); shown.real = shown.attacker = shown.realStart = null; fetch("/api/reset", { method: "POST" }); });

function fit() {
  const z = Math.min(1, innerWidth / 1600, innerHeight / 1000);
  document.body.style.zoom = z;
  document.body.style.height = innerHeight / z + "px";
}
addEventListener("resize", fit); fit();

const es = new EventSource("/api/stream");
es.onmessage = (m) => { S = JSON.parse(m.data); render(); };
