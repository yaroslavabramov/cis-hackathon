const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const aed = (n) => "AED " + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const short = (n) => "AED " + Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
let S = null, clockBase = 0, clockAt = 0, seen = new Set();
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
    const cls = { diverted: "diverted", alert: "alert", devin: "devin", release: "release", fraud: "alert" }[e.kind] || "sys";
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
  const rowH = 54, h = Math.max(120, d.length * rowH), W = 600, X = 250, max = Math.max(...d.map((x) => x.total));
  const vy = h / 2, color = inc.diverted ? "var(--mirage)" : "var(--red)";
  const cut = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
  const links = d.map((x, i) => {
    const y = i * rowH + 23, w = 2 + 10 * (x.total / max);
    return `<path d="M140 ${vy} C 200 ${vy}, 190 ${y}, ${X} ${y}" stroke="${color}" stroke-opacity=".55" stroke-width="${w}" fill="none"/>`;
  }).join("");
  const nodes = d.map((x, i) => {
    const y = i * rowH;
    const ref = x.reference && x.reference.startsWith("USDT") ? x.reference : x.iban;
    return `<g class="node"><rect x="${X}" y="${y}" width="${W - X - 2}" height="46" rx="10"/>
      <text x="${X + 12}" y="${y + 19}">${esc(cut(x.name, 30))}</text>
      <text class="m" x="${X + 12}" y="${y + 36}">${esc(x.country)} · ${esc(cut(ref, 36))}</text>
      <text class="a" x="${W - 14}" y="${y + 19}" text-anchor="end">${short(x.total)}</text>
      <text class="m" x="${W - 14}" y="${y + 36}" text-anchor="end">${x.count} transfer${x.count > 1 ? "s" : ""}</text></g>`;
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

function renderStage() {
  const inc = S.incident, stage = $("#stage");
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
  const off = !inc.diverted, released = inc.status === "released", fraud = inc.status === "confirmed_fraud";
  const sent = inc.balances.real < (shown.realStart ?? inc.balances.real);
  const state = released ? "RELEASED AFTER CUSTOMER CONFIRMATION" : fraud ? "FRAUD CONFIRMED · REPORT FILED" :
    off ? "ATTACK IN PROGRESS · PROTECTION OFF" : "ATTACKER TRAPPED IN A FAKE BANK";
  const first = inc.name.split(" ")[0];
  const title = off ? `Protection is off: the attacker is moving ${first}'s real money out of the bank` :
    released ? "Held transfers posted to the real account" :
    `The attacker was moved into a fake copy of the bank. He thinks he is stealing; ${first}'s real money hasn't moved.`;
  const drained = off && inc.balances.real < 1;
  const realNote = released ? "held transfers posted after the customer confirmed" : off ? (drained ? "drained: the money really left the bank" : "real money is leaving the bank") : "in the real bank database · not a single dirham moved";
  const fakeNote = inc.diverted ? `fake balance in the shadow copy · ${inc.held.length} transfers "approved", none of them real` : "no deception: he sees the real balance";
  const sigs = inc.signals.map((s) => `<div class="sig"><span class="w">+${s.weight}</span><div><b>${esc(s.title)}</b><div>${esc(s.detail)}</div></div></div>`).join("");
  const eps = inc.endpoints.map((e) => `<span class="${e.includes("/v1/transfers") ? "hot" : ""}">${esc(e)}</span>`).join("");

  stage.innerHTML = `
    <div class="banner ${off ? "off" : ""} ${released ? "released" : ""}">
      <div><div class="state">${state}</div><div class="title">${title}</div>
        <div class="meta"><span>Session <b class="mono">${esc(inc.id)}</b></span><span>${esc(inc.name)}</span>
        <span>device <b class="mono">${esc(inc.device_id)}</b></span><span>IP <b class="mono">${esc(inc.ip)}</b></span>
        <span>UA ${esc(inc.user_agent)}</span><span>login ${esc(inc.started)}</span>
        ${inc.diverted_at ? `<span>diverted <b>${esc(inc.diverted_at)}</b></span>` : ""}</div></div>
      <div class="gauge" style="--v:${inc.score};--c:${inc.score >= S.threshold ? "var(--red)" : "var(--amber)"}"><span>${inc.score}</span><small>RISK</small></div>
    </div>
    <div class="balances">
      <div class="bal real ${drained || (off && sent) ? "drained" : ""}"><div class="lbl">${esc(first)}'s real balance</div><div class="amt" id="amt-real"></div><div class="note">${realNote}</div></div>
      <div class="bal fake"><div class="lbl">What the attacker sees on his screen</div><div class="amt" id="amt-fake"></div><div class="note">${fakeNote}</div></div>
    </div>
    <div class="grid2">
      <div class="panel"><div class="panel-h"><h2>Why this session was flagged</h2><span class="muted">threshold ${S.threshold}</span></div>
        <div class="meter"><i style="width:${inc.score}%"></i><em style="left:${S.threshold}%"></em></div>
        <div class="signals">${sigs}</div></div>
      <div class="panel flow"><div class="panel-h"><h2>Where the attacker tried to send the money</h2><span class="muted">${inc.destinations.length} destinations</span></div>
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
  const post = (url) => fetch(url, { method: "POST" });
  $("#release")?.addEventListener("click", () => post(`/api/incidents/${inc.id}/release`));
  $("#fraud")?.addEventListener("click", () => post(`/api/incidents/${inc.id}/fraud`));
  $("#devin-btn")?.addEventListener("click", () => post(`/api/incidents/${inc.id}/devin`));
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
