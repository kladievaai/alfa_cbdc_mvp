/* Альфа-CBDC — клиентская логика (ванильный JS, без зависимостей). */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const fmtRub = n => new Intl.NumberFormat("ru-RU", {
  style: "currency", currency: "RUB", maximumFractionDigits: 2
}).format(n).replace("₽", "цифр. ₽");
const fmtNum = n => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(n);
const fmtDate = iso => iso ? new Date(iso).toLocaleString("ru-RU") : "—";

async function api(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  const text = await r.text();
  const data = text ? JSON.parse(text) : null;
  if (!r.ok) {
    const msg = (data && (data.detail || data.message)) || r.statusText;
    throw new Error(msg);
  }
  return data;
}

// ---------- Toast ----------
function toast(msg, type = "info") {
  const wrap = $("#toast-wrap");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

// ---------- Глобальное состояние ----------
const state = {
  clients: [],
  counterparties: [],
  corridors: [],
  currentClientId: null,
  contracts: [],
  payments: [],
};

// ---------- Вкладки ----------
function activateTab(name) {
  $$(".tab").forEach(s => s.classList.toggle("active", s.dataset.tab === name));
  $$("nav.tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "dashboard") loadDashboard();
  if (name === "clients") renderClients();
  if (name === "contracts") renderContractsTab();
  if (name === "payments") renderPaymentsTab();
  if (name === "smart-contracts") renderSmartContractsTab();
  if (name === "vc") renderVCTab();
  if (name === "audit") loadAudit();
}

// ---------- Дашборд ----------
async function loadDashboard() {
  try {
    const stats = await api("GET", "/api/dashboard");
    $("#kpi-clients").textContent = stats.clients;
    $("#kpi-wallets").textContent = stats.wallets;
    $("#kpi-contracts").textContent = stats.contracts;
    $("#kpi-settled").textContent = stats.payments_settled;
    $("#kpi-pending").textContent = stats.payments_pending;
    $("#kpi-sc-active").textContent = stats.smart_contracts_active;
    $("#kpi-volume").textContent = fmtRub(stats.total_volume_drub);
    $("#kpi-fees").textContent = fmtRub(stats.total_fees_drub);
    $("#kpi-loyalty").textContent = stats.loyalty_clients;
  } catch (e) { toast(e.message, "error"); }
}

// ---------- Загрузка коридоров ----------
async function loadCorridors() {
  state.corridors = await api("GET", "/api/corridors");
  // заполнить селект коридоров
  const sel = $("#payment-corridor");
  const cpSel = $("#cp-country");
  sel.innerHTML = "";
  cpSel.innerHTML = "";
  for (const c of state.corridors) {
    const opt = document.createElement("option");
    opt.value = c.code;
    opt.textContent = `${c.flag} ${c.name} — ${c.currency_code} (курс 1 ${c.currency_code} = ${c.rate_to_drub} цифр. ₽)`;
    sel.appendChild(opt);
    const opt2 = opt.cloneNode(true);
    cpSel.appendChild(opt2);
  }
  // рендер карточек коридоров на дашборде
  const grid = $("#corridors-grid");
  grid.innerHTML = "";
  for (const c of state.corridors) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div style="font-size:30px">${c.flag}</div>
      <h3>${c.name}</h3>
      <div class="muted">${c.central_bank}</div>
      <div class="divider"></div>
      <div class="flex between"><span>Валюта:</span><b>${c.currency_code}</b></div>
      <div class="flex between"><span>Кросс-курс:</span><span class="mono">1 ${c.currency_code} = ${c.rate_to_drub} цифр. ₽</span></div>
      <div class="flex between"><span>Доля адресного объёма:</span><b>${c.share_pct}%</b></div>
    `;
    grid.appendChild(card);
  }
}

// ---------- Клиенты ----------
async function loadClients() {
  state.clients = await api("GET", "/api/clients");
  const sel = $("#current-client");
  sel.innerHTML = `<option value="">— Выберите клиента —</option>`;
  for (const c of state.clients) {
    const o = document.createElement("option");
    o.value = c.id;
    o.textContent = `${c.name} (ИНН ${c.inn}, ${c.segment})${c.kyc_passed ? " ✓" : ""}`;
    sel.appendChild(o);
  }
  if (state.clients.length && !state.currentClientId) {
    state.currentClientId = state.clients[0].id;
    sel.value = state.currentClientId;
    await onClientChange();
  } else if (state.currentClientId) {
    sel.value = state.currentClientId;
  }
}

async function renderClients() {
  await loadClients();
  const tbody = $("#clients-tbody");
  tbody.innerHTML = "";
  for (const c of state.clients) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${c.name}</b><div class="muted">ИНН ${c.inn}</div></td>
      <td><span class="badge ${segBadge(c.segment)}">${segLabel(c.segment)}</span></td>
      <td>${c.kyc_passed
        ? `<span class="badge ok">KYC пройден</span>`
        : `<span class="badge pending">KYC не пройден</span>`}</td>
      <td>${c.contact_email || ""}<div class="muted">${c.contact_phone || ""}</div></td>
      <td class="right">
        ${!c.kyc_passed ? `<button class="btn ghost" onclick="runKyc(${c.id})">Запустить KYC</button>` : ""}
        <button class="btn" onclick="openWallet(${c.id})">Открыть кошелёк</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function segLabel(s) { return s === "small" ? "Малый" : s === "medium" ? "Средний" : "Крупный"; }
function segBadge(s) { return s === "small" ? "gray" : s === "medium" ? "info" : "ok"; }

async function createClient(ev) {
  ev.preventDefault();
  const form = ev.target;
  try {
    await api("POST", "/api/clients", {
      inn: form.inn.value, name: form.name.value, segment: form.segment.value,
      contact_email: form.email.value, contact_phone: form.phone.value,
    });
    toast("Клиент создан.", "success");
    form.reset();
    await renderClients();
  } catch (e) { toast(e.message, "error"); }
}

async function runKyc(id) {
  try {
    await api("POST", `/api/clients/${id}/kyc`);
    toast("KYC/KYB пройден по ФЗ-115.", "success");
    await renderClients();
  } catch (e) { toast(e.message, "error"); }
}

async function openWallet(id) {
  try {
    await api("POST", `/api/clients/${id}/wallet`);
    toast("Кошелёк цифрового рубля открыт на платформе Банка России.", "success");
    if (state.currentClientId === id) await refreshWallet();
  } catch (e) { toast(e.message, "error"); }
}

// ---------- Текущий клиент ----------
async function onClientChange() {
  const id = parseInt($("#current-client").value || "0", 10);
  state.currentClientId = id || null;
  await refreshWallet();
  await loadContracts();
  await loadPayments();
}

async function refreshWallet() {
  const box = $("#wallet-box");
  if (!state.currentClientId) { box.innerHTML = `<div class="empty">Клиент не выбран.</div>`; return; }
  try {
    const w = await api("GET", `/api/clients/${state.currentClientId}/wallet`);
    box.innerHTML = `
      <div class="flex between" style="align-items:flex-start">
        <div>
          <div class="muted">ID кошелька (платформа Банка России)</div>
          <div class="mono">${w.cbr_wallet_id}</div>
          <div class="muted" style="margin-top:6px">Открыт: ${fmtDate(w.opened_at)}</div>
        </div>
        <div class="right">
          <div class="kpi"><span class="label">Доступно</span>
            <span class="value">${fmtRub(w.balance_drub)}</span></div>
          <div class="muted" style="margin-top:4px">В эскроу: ${fmtRub(w.blocked_drub)}</div>
        </div>
      </div>
    `;
  } catch (e) {
    box.innerHTML = `<div class="empty">У клиента ещё нет кошелька. Откройте его во вкладке «Клиенты».</div>`;
  }
}

async function topUp() {
  const amt = parseFloat($("#topup-amount").value);
  if (!amt) return;
  try {
    await api("POST", `/api/clients/${state.currentClientId}/wallet/top-up`, { amount: amt });
    toast(`Пополнено на ${fmtRub(amt)}.`, "success");
    $("#topup-amount").value = "";
    await refreshWallet(); await loadDashboard();
  } catch (e) { toast(e.message, "error"); }
}

async function withdraw() {
  const amt = parseFloat($("#withdraw-amount").value);
  if (!amt) return;
  try {
    await api("POST", `/api/clients/${state.currentClientId}/wallet/withdraw`, { amount: amt });
    toast(`Выведено ${fmtRub(amt)} в безналичную форму.`, "success");
    $("#withdraw-amount").value = "";
    await refreshWallet(); await loadDashboard();
  } catch (e) { toast(e.message, "error"); }
}

// ---------- Контрагенты ----------
async function loadCounterparties() {
  state.counterparties = await api("GET", "/api/counterparties");
  const sel = $("#contract-counterparty");
  sel.innerHTML = "";
  for (const cp of state.counterparties) {
    const o = document.createElement("option");
    o.value = cp.id;
    o.textContent = `${cp.name} (${cp.country_code}) — ${cp.bank_name || ""}`;
    sel.appendChild(o);
  }
}

async function renderContractsTab() {
  await loadCounterparties();
  await loadContracts();
  const tbody = $("#cps-tbody");
  tbody.innerHTML = "";
  for (const cp of state.counterparties) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${cp.name}</b></td>
      <td>${cp.country_code}</td>
      <td>${cp.bank_name || ""}</td>
      <td class="mono">${cp.cbdc_wallet_id || ""}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function createCounterparty(ev) {
  ev.preventDefault();
  const form = ev.target;
  try {
    await api("POST", "/api/counterparties", {
      name: form.name.value,
      country_code: form.country.value,
      bank_name: form.bank.value,
    });
    toast("Контрагент добавлен.", "success");
    form.reset();
    await renderContractsTab();
  } catch (e) { toast(e.message, "error"); }
}

async function loadContracts() {
  if (!state.currentClientId) { state.contracts = []; renderContractsList(); return; }
  state.contracts = await api("GET", `/api/clients/${state.currentClientId}/contracts`);
  renderContractsList();
  // обновить select контрактов в платежах
  const sel = $("#payment-contract");
  if (sel) {
    sel.innerHTML = "";
    for (const c of state.contracts) {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = `${c.contract_number} — ${c.operation_type} (${fmtRub(c.total_amount)})`;
      sel.appendChild(o);
    }
  }
}

function renderContractsList() {
  const tbody = $("#contracts-tbody");
  tbody.innerHTML = "";
  if (!state.contracts.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted right" style="text-align:center">Контрактов пока нет.</td></tr>`;
    return;
  }
  for (const c of state.contracts) {
    const cp = state.counterparties.find(x => x.id === c.counterparty_id);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${c.contract_number}</b><div class="muted mono">УНК: ${c.uk_number || "—"}</div></td>
      <td>${c.operation_type}</td>
      <td>${cp ? `${cp.name} (${cp.country_code})` : "—"}</td>
      <td class="right">${fmtRub(c.total_amount)}</td>
      <td>${fmtDate(c.contract_date)}</td>
      <td><span class="badge ok">${c.status}</span></td>
    `;
    tbody.appendChild(tr);
  }
}

async function createContract(ev) {
  ev.preventDefault();
  if (!state.currentClientId) { toast("Выберите клиента.", "error"); return; }
  const form = ev.target;
  try {
    await api("POST", `/api/clients/${state.currentClientId}/contracts`, {
      counterparty_id: parseInt(form.counterparty.value, 10),
      contract_number: form.number.value,
      contract_date: new Date(form.date.value).toISOString(),
      operation_type: form.operation.value,
      total_amount: parseFloat(form.amount.value),
      currency: form.currency.value,
      description: form.description.value,
    });
    toast("Контракт зарегистрирован и поставлен на учёт (Инструкция 181-И).", "success");
    form.reset();
    await loadContracts();
    await loadDashboard();
  } catch (e) { toast(e.message, "error"); }
}

// ---------- Платежи ----------
async function renderPaymentsTab() {
  await loadContracts();
  await loadPayments();
}

async function loadPayments() {
  if (!state.currentClientId) { state.payments = []; renderPaymentsList(); return; }
  state.payments = await api("GET", `/api/clients/${state.currentClientId}/payments`);
  renderPaymentsList();
}

function renderPaymentsList() {
  const tbody = $("#payments-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!state.payments.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align:center">Платежей пока нет.</td></tr>`;
    return;
  }
  for (const p of state.payments) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>#${p.id}</td>
      <td>${p.payment_type === "smart_contract"
            ? `<span class="badge info">Смарт-контракт</span>`
            : `<span class="badge ok">Мгновенный</span>`}</td>
      <td>${p.corridor}</td>
      <td class="right">${fmtNum(p.amount_foreign)} ${p.foreign_currency}</td>
      <td class="right">${fmtRub(p.amount_drub)}</td>
      <td class="right muted">${fmtRub(p.fee_amount_drub)} (${(p.fee_pct * 100).toFixed(2)}%)</td>
      <td>${paymentStatusBadge(p.status)}<div class="muted mono">${p.cbr_tx_id || ""}</div></td>
      <td>${fmtDate(p.initiated_at)}<div class="muted">→ ${fmtDate(p.settled_at)}</div></td>
    `;
    tbody.appendChild(tr);
  }
}

function paymentStatusBadge(s) {
  const map = {
    settled: ["ok", "Исполнен"],
    initiated: ["pending", "Инициирован"],
    compliance_passed: ["pending", "Комплаенс пройден"],
    executing: ["pending", "Исполняется"],
    escrow: ["info", "В эскроу"],
    refunded: ["gray", "Возвращён"],
    failed: ["error", "Ошибка"],
  };
  const [cls, label] = map[s] || ["gray", s];
  return `<span class="badge ${cls}">${label}</span>`;
}

async function calcQuote() {
  const box = $("#quote-box");
  if (!state.currentClientId) { box.innerHTML = ""; return; }
  const corridor = $("#payment-corridor").value;
  const amt = parseFloat($("#payment-amount").value);
  if (!corridor || !amt) { box.innerHTML = ""; return; }
  try {
    const q = await api(
      "GET",
      `/api/clients/${state.currentClientId}/quote?corridor=${corridor}&amount_foreign=${amt}`
    );
    box.innerHTML = `
      <div class="row"><span>Курс</span><b class="mono">1 ${q.foreign_currency} = ${q.rate} цифр. ₽</b></div>
      <div class="row"><span>Сумма в ${q.foreign_currency}</span><b>${fmtNum(q.amount_foreign)}</b></div>
      <div class="row"><span>Сумма в цифровых рублях</span><b>${fmtRub(q.amount_drub)}</b></div>
      <div class="row"><span>Комиссия Альфа-Банка (${(q.fee_pct * 100).toFixed(2)}%)</span>
                       <b>${fmtRub(q.fee_amount_drub)}</b></div>
      <div class="row total"><span>К списанию с кошелька</span><b>${fmtRub(q.total_drub)}</b></div>
    `;
  } catch (e) {
    box.innerHTML = `<div class="muted">${e.message}</div>`;
  }
}

async function submitPayment(ev) {
  ev.preventDefault();
  if (!state.currentClientId) { toast("Выберите клиента.", "error"); return; }
  const form = ev.target;
  try {
    const p = await api("POST", `/api/clients/${state.currentClientId}/payments`, {
      contract_id: parseInt(form.contract.value, 10),
      corridor: form.corridor.value,
      amount_foreign: parseFloat(form.amount.value),
      payment_type: form.type.value,
      deadline_days: parseInt(form.deadline.value || "30", 10),
    });
    if (p.payment_type === "smart_contract") {
      toast(`Смарт-контракт создан. Эскроу: ${fmtRub(p.amount_drub + p.fee_amount_drub)}.`, "success");
    } else {
      toast(`Платёж исполнен атомарной транзакцией: CBR ↔ партнёр.`, "success");
    }
    form.reset();
    $("#quote-box").innerHTML = "";
    await refreshWallet();
    await loadPayments();
    await loadDashboard();
  } catch (e) { toast(e.message, "error"); }
}

// ---------- Смарт-контракты ----------
async function renderSmartContractsTab() {
  await loadPayments();
  const list = $("#sc-list");
  list.innerHTML = "";
  const scPayments = state.payments.filter(p => p.payment_type === "smart_contract");
  if (!scPayments.length) {
    list.innerHTML = `<div class="empty">У клиента нет смарт-контрактов. Создайте платёж типа «Безопасная сделка».</div>`;
    return;
  }
  for (const p of scPayments) {
    try {
      const sc = await api("GET", `/api/payments/${p.id}/smart-contract`);
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="flex between" style="align-items:flex-start">
          <div>
            <h3 style="margin:0">Платёж #${p.id} · ${p.corridor} · ${fmtNum(p.amount_foreign)} ${p.foreign_currency}</h3>
            <div class="muted">Эскроу: <b>${fmtRub(sc.escrow_balance_drub)}</b>
              · Дедлайн: ${fmtDate(sc.deadline)}
              · Статус: ${scStatusBadge(sc.status)}</div>
          </div>
          ${sc.status === "active" ? `
            <button class="btn neutral" onclick="refundSC(${sc.id})">Принудительный возврат</button>` : ""}
        </div>
        <div class="divider"></div>
        ${sc.conditions.map(c => `
          <div class="condition ${c.is_fulfilled ? "done" : ""}">
            <span class="icon">${c.is_fulfilled ? "✓" : "·"}</span>
            <div style="flex:1">
              <div>${c.label}</div>
              <div class="meta">${c.is_fulfilled
                ? `Источник: ${c.source_system || "—"} · Док.: ${c.document_ref || "—"} · ${fmtDate(c.fulfilled_at)}`
                : `Ожидает подтверждения`}</div>
            </div>
            ${!c.is_fulfilled && sc.status === "active"
              ? `<button class="btn ghost"
                          onclick="fulfillCondition(${sc.id}, '${c.code}')">Подтвердить</button>`
              : ""}
          </div>
        `).join("")}
      `;
      list.appendChild(card);
    } catch (e) { /* silent */ }
  }
}

function scStatusBadge(s) {
  const map = { active: ["pending", "Активный"], executed: ["ok", "Исполнен"],
                refunded: ["gray", "Возвращён"], expired: ["error", "Истёк"] };
  const [cls, label] = map[s] || ["gray", s];
  return `<span class="badge ${cls}">${label}</span>`;
}

async function fulfillCondition(scId, code) {
  const labelMap = {
    transport_doc: ["клиент", "транспортная накладная"],
    customs_cleared: ["ФТС России", "декларация ГТД"],
    goods_accepted: ["клиент", "акт приёмки"],
  };
  const [source, docName] = labelMap[code] || ["клиент", "документ"];
  const ref = prompt(`Введите номер документа (${docName}):`, `${docName.toUpperCase().replaceAll(' ','-')}-${Math.floor(Math.random()*900000+100000)}`);
  if (!ref) return;
  try {
    await api("POST", `/api/smart-contracts/${scId}/conditions/fulfill`, {
      code, document_ref: ref, source_system: source,
    });
    toast("Условие подтверждено.", "success");
    await renderSmartContractsTab();
    await refreshWallet();
    await loadDashboard();
  } catch (e) { toast(e.message, "error"); }
}

async function refundSC(scId) {
  if (!confirm("Произвести возврат средств клиенту?")) return;
  try {
    await api("POST", `/api/smart-contracts/${scId}/refund`);
    toast("Средства возвращены на основной кошелёк.", "success");
    await renderSmartContractsTab();
    await refreshWallet();
    await loadDashboard();
  } catch (e) { toast(e.message, "error"); }
}

// ---------- Валютный контроль ----------
async function renderVCTab() {
  await loadPayments();
  const list = $("#vc-list");
  list.innerHTML = "";
  if (!state.payments.length) {
    list.innerHTML = `<div class="empty">Платежей нет — записи валютного контроля появятся после первой операции.</div>`;
    return;
  }
  for (const p of state.payments) {
    try {
      const rec = await api("GET", `/api/payments/${p.id}/currency-control`);
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="flex between">
          <div>
            <h3 style="margin:0">Платёж #${p.id} · СПД ${rec.spd_number}</h3>
            <div class="muted">УНК: <span class="mono">${rec.payload?.unk || "—"}</span> ·
              Сформировано: ${fmtDate(rec.submitted_at)}</div>
          </div>
          <div>
            <span class="badge ${rec.submitted_to_cbr ? "ok" : "pending"}">ЦБ РФ</span>
            <span class="badge ${rec.submitted_to_fns ? "ok" : "pending"}">ФНС России</span>
          </div>
        </div>
        <div class="divider"></div>
        <details>
          <summary>Полный пакет документов (181-И)</summary>
          <pre>${JSON.stringify(rec.payload, null, 2)}</pre>
        </details>
      `;
      list.appendChild(card);
    } catch { /* not found */ }
  }
}

// ---------- Аудит ----------
async function loadAudit() {
  const rows = await api("GET", "/api/audit?limit=100");
  const tbody = $("#audit-tbody");
  tbody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${fmtDate(r.ts)}</td>
      <td>${r.actor}</td>
      <td><b>${r.action}</b></td>
      <td>${r.entity} #${r.entity_id ?? ""}</td>
      <td class="mono" style="max-width:480px;overflow:auto"><code>${JSON.stringify(r.details)}</code></td>
    `;
    tbody.appendChild(tr);
  }
}

// ---------- Init ----------
async function init() {
  $$("nav.tabs button").forEach(b => b.addEventListener("click", () => activateTab(b.dataset.tab)));
  $("#current-client").addEventListener("change", onClientChange);
  $("#client-form").addEventListener("submit", createClient);
  $("#cp-form").addEventListener("submit", createCounterparty);
  $("#contract-form").addEventListener("submit", createContract);
  $("#payment-form").addEventListener("submit", submitPayment);
  $("#payment-corridor").addEventListener("change", calcQuote);
  $("#payment-amount").addEventListener("input", calcQuote);
  $("#topup-btn").addEventListener("click", topUp);
  $("#withdraw-btn").addEventListener("click", withdraw);

  await loadCorridors();
  await loadClients();
  await loadCounterparties();
  await loadDashboard();
  activateTab("dashboard");
}
init();
