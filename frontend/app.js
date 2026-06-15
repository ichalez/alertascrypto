"use strict";

const SIGNAL_LABELS = { simple: "Entrada", turn: "Giro", exit: "Salida", divergence: "Diverg." };
const COOLDOWNS = [
  [300, "5 min"], [600, "10 min"], [900, "15 min"], [1800, "30 min"], [3600, "1 hora"],
];

let CONFIG = null;

const $ = (s) => document.querySelector(s);
const api = (p, opts) => fetch("/api" + p, opts).then((r) => r.json());

// ---------------- Navegación ----------------
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("tab--active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("view--active"));
    t.classList.add("tab--active");
    $("#view-" + t.dataset.view).classList.add("view--active");
    if (t.dataset.view === "history") loadHistory();
  });
});

// ---------------- Master on/off ----------------
$("#masterBtn").addEventListener("click", async () => {
  if (!CONFIG) return;
  CONFIG.running = !CONFIG.running;
  renderMaster();
  await api("/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ running: CONFIG.running }) });
});
function renderMaster() {
  const b = $("#masterBtn");
  b.dataset.running = CONFIG.running;
  $("#masterTxt").textContent = CONFIG.running ? "En marcha" : "Pausado";
}

// ---------------- Panel en vivo ----------------
function pct(v) { return Math.max(0, Math.min(100, v)); }

function renderPanel(state) {
  const wrap = $("#cards");
  if (!CONFIG) return;
  let buy = 0, sell = 0, neu = 0;
  const frag = document.createDocumentFragment();

  for (const sym of Object.keys(CONFIG.assets)) {
    const a = CONFIG.assets[sym];
    const s = (state.assets || {})[sym];
    const base = sym.replace("USDT", "");
    const el = document.createElement("article");
    el.className = "asset";

    if (!a.enabled) {
      el.dataset.zone = "off";
      el.innerHTML = `<div class="asset__head"><span class="asset__ticker">${base}</span></div>
        <div class="asset__badge asset__badge--off">Desactivado</div>`;
      frag.appendChild(el); continue;
    }
    if (!s || s.rsi == null) {
      el.dataset.zone = "neutral";
      el.innerHTML = `<div class="asset__head"><span class="asset__ticker">${base}</span></div>
        <div class="asset__meta">esperando datos…</div>`;
      frag.appendChild(el); continue;
    }

    el.dataset.zone = s.zone;
    if (s.zone === "oversold") buy++; else if (s.zone === "overbought") sell++; else neu++;

    const mtf = s.mtf_rsi != null ? ` · ${CONFIG.mtf_interval} ${Math.round(s.mtf_rsi)}` : "";
    let badge = "";
    if (s.zone === "oversold") badge = `<div class="asset__badge asset__badge--buy">Sobreventa — posible compra</div>`;
    else if (s.zone === "overbought") badge = `<div class="asset__badge asset__badge--sell">Sobrecompra — posible venta</div>`;

    el.innerHTML = `
      <div class="asset__head">
        <span class="asset__ticker">${base}</span>
        <span class="asset__price mono">${fmtPrice(s.price)}</span>
      </div>
      <div class="asset__rsi">
        <span class="asset__rsi-val mono">${s.rsi.toFixed(1)}</span>
        <span class="asset__rsi-label">RSI ${CONFIG.interval}</span>
      </div>
      <div class="track">
        <div class="track__zone track__zone--os" style="width:${a.oversold}%"></div>
        <div class="track__zone track__zone--ob" style="left:${a.overbought}%;right:0"></div>
        <div class="track__marker" style="left:${pct(s.rsi)}%"></div>
      </div>
      <div class="asset__meta">SV ${a.oversold} · SC ${a.overbought}${mtf}</div>
      ${badge}`;
    frag.appendChild(el);
  }
  wrap.innerHTML = "";
  wrap.appendChild(frag);
  $("#sumBuy").textContent = buy;
  $("#sumSell").textContent = sell;
  $("#sumNeu").textContent = neu;
}

function fmtPrice(p) {
  if (p >= 1000) return p.toLocaleString("es-ES", { maximumFractionDigits: 0 }) + "";
  if (p >= 1) return p.toFixed(2);
  return p.toPrecision(4);
}

async function poll() {
  try {
    const state = await api("/state");
    renderPanel(state);
  } catch (e) { /* reintenta en el siguiente ciclo */ }
}

// ---------------- Ajustes ----------------
function fillSettings() {
  $("#pollSeconds").value = String(CONFIG.poll_seconds);
  $("#mtfFilter").checked = !!CONFIG.mtf_filter;
  $("#mtfInterval").value = CONFIG.mtf_interval;
  $("#stopMult").value = String(CONFIG.stop_atr_mult);
  $("#rrRatio").value = String(CONFIG.rr_ratio);
  $("#quietEnabled").checked = !!CONFIG.schedule.enabled;
  $("#quietStart").value = CONFIG.schedule.quiet_start;
  $("#quietEnd").value = CONFIG.schedule.quiet_end;
  $("#tgToken").value = CONFIG.telegram.token || "";
  $("#tgChat").value = CONFIG.telegram.chat_id || "";
  $("#chTelegram").checked = !!CONFIG.channels.telegram;
  $("#chPush").checked = !!CONFIG.channels.push;
  buildAssetList();
}

function buildAssetList() {
  const wrap = $("#assetList");
  wrap.innerHTML = "";
  for (const sym of Object.keys(CONFIG.assets)) {
    const a = CONFIG.assets[sym];
    const base = sym.replace("USDT", "");
    const row = document.createElement("div");
    row.className = "arow";
    const cdOpts = COOLDOWNS.map(([v, l]) => `<option value="${v}" ${a.cooldown_seconds == v ? "selected" : ""}>${l}</option>`).join("");
    const sigChip = (k) => `<label class="chip"><input type="checkbox" data-sig="${k}" ${a.signals[k] ? "checked" : ""}>${SIGNAL_LABELS[k]}</label>`;
    row.innerHTML = `
      <div class="arow__head">
        <span class="arow__tk"><span class="arow__chev">›</span>${base}</span>
        <input type="checkbox" class="switch" data-enabled ${a.enabled ? "checked" : ""}>
      </div>
      <div class="arow__body">
        <div class="arow__grid">
          <label class="field"><span>Sobreventa ≤</span><input type="number" class="ctl" data-os min="5" max="50" value="${a.oversold}"></label>
          <label class="field"><span>Sobrecompra ≥</span><input type="number" class="ctl" data-ob min="50" max="95" value="${a.overbought}"></label>
        </div>
        <label class="field"><span>Silencio entre avisos</span><select class="ctl ctl--full" data-cd>${cdOpts}</select></label>
        <span class="field" style="margin-bottom:6px"><span>Señales</span></span>
        <div class="sigs">${sigChip("simple")}${sigChip("turn")}${sigChip("exit")}${sigChip("divergence")}</div>
      </div>`;
    row.dataset.sym = sym;
    row.querySelector(".arow__head").addEventListener("click", (e) => {
      if (e.target.matches("[data-enabled]")) return;
      row.classList.toggle("arow--open");
    });
    wrap.appendChild(row);
  }
}

function gatherSettings() {
  CONFIG.poll_seconds = Number($("#pollSeconds").value);
  CONFIG.mtf_filter = $("#mtfFilter").checked;
  CONFIG.mtf_interval = $("#mtfInterval").value;
  CONFIG.stop_atr_mult = Number($("#stopMult").value);
  CONFIG.rr_ratio = Number($("#rrRatio").value);
  CONFIG.schedule.enabled = $("#quietEnabled").checked;
  CONFIG.schedule.quiet_start = $("#quietStart").value;
  CONFIG.schedule.quiet_end = $("#quietEnd").value;
  CONFIG.telegram.token = $("#tgToken").value.trim();
  CONFIG.telegram.chat_id = $("#tgChat").value.trim();
  CONFIG.channels.telegram = $("#chTelegram").checked;
  CONFIG.channels.push = $("#chPush").checked;
  document.querySelectorAll(".arow").forEach((row) => {
    const a = CONFIG.assets[row.dataset.sym];
    a.enabled = row.querySelector("[data-enabled]").checked;
    a.oversold = Number(row.querySelector("[data-os]").value);
    a.overbought = Number(row.querySelector("[data-ob]").value);
    a.cooldown_seconds = Number(row.querySelector("[data-cd]").value);
    row.querySelectorAll("[data-sig]").forEach((c) => { a.signals[c.dataset.sig] = c.checked; });
  });
}

$("#saveBtn").addEventListener("click", async () => {
  gatherSettings();
  const btn = $("#saveBtn");
  btn.textContent = "Guardando…";
  await api("/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CONFIG) });
  btn.textContent = "Guardado ✓";
  poll();
  setTimeout(() => (btn.textContent = "Guardar cambios"), 1400);
});

// ---------------- Prueba de avisos ----------------
$("#testBtn").addEventListener("click", async () => {
  const m = $("#testMsg");
  m.textContent = "Enviando…"; m.className = "hint";
  gatherSettings();
  await api("/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CONFIG) });
  const res = await api("/test", { method: "POST" });
  const tg = res.telegram.ok ? "Telegram ✓" : "Telegram ✕ (" + res.telegram.detail + ")";
  const ps = res.push.sent > 0 ? `Push ✓ (${res.push.sent})` : "Push: sin dispositivos";
  m.textContent = `${tg} · ${ps}`;
  m.className = "hint " + (res.telegram.ok ? "hint--ok" : "hint--err");
});

// ---------------- Web Push ----------------
$("#pushBtn").addEventListener("click", subscribePush);

function urlB64ToUint8(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function subscribePush() {
  const m = $("#testMsg");
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      m.textContent = "Este navegador no soporta push."; m.className = "hint hint--err"; return;
    }
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { m.textContent = "Permiso de notificaciones denegado."; m.className = "hint hint--err"; return; }
    const reg = await navigator.serviceWorker.ready;
    const { publicKey } = await api("/push/key");
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8(publicKey),
    });
    await api("/push/subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(sub) });
    m.textContent = "Push activado en este dispositivo ✓"; m.className = "hint hint--ok";
    $("#chPush").checked = true;
  } catch (e) {
    m.textContent = "No se pudo activar push: " + e.message; m.className = "hint hint--err";
  }
}

// ---------------- Historial ----------------
async function loadHistory() {
  const wrap = $("#history");
  const items = await api("/history");
  if (!items.length) { wrap.innerHTML = `<p class="empty">Aún no hay alarmas. Cuando salte una señal aparecerá aquí.</p>`; return; }
  wrap.innerHTML = items.map((h) => {
    const lv = h.levels;
    const levelsHtml = lv ? `<div class="hitem__lv">
        <span>E ${fmtLv(lv.entry)}</span>
        <span class="hitem__lv--stop">SL ${fmtLv(lv.stop)}</span>
        <span class="hitem__lv--tp">TP ${fmtLv(lv.tp)}</span>
      </div>` : "";
    return `
    <div class="hitem">
      <div class="hitem__side hitem__side--${h.side}"></div>
      <div class="hitem__main">
        <div class="hitem__top">
          <span class="hitem__tk">${h.base}</span>
          <span class="hitem__act hitem__act--${h.side}">${h.action}</span>
        </div>
        <span class="hitem__sub">${h.label}</span>
        ${levelsHtml}
      </div>
      <div>
        <span class="hitem__rsi mono">${h.rsi}</span>
        <span class="hitem__time">${h.time}</span>
      </div>
    </div>`;
  }).join("");
}

function fmtLv(v) {
  if (v == null) return "—";
  if (v >= 100) return v.toFixed(2);
  if (v >= 1) return v.toFixed(3);
  return v.toFixed(5);
}

$("#clearBtn").addEventListener("click", async () => {
  await api("/history", { method: "DELETE" });
  loadHistory();
});

// ---------------- Init ----------------
async function init() {
  CONFIG = await api("/config");
  renderMaster();
  fillSettings();
  await poll();
  setInterval(poll, 5000);
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}
init();
