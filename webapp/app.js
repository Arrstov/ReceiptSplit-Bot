const telegram = window.Telegram?.WebApp;

const state = {
  me: null,
  stats: null,
  dashboard: { events: [], receipts: [] },
  events: [],
  recentReceipts: [],
  groups: [],
  contacts: [],
  contactsRequestLink: null,
  contactsRequestTgLink: null,
  createParticipants: [],
  createMode: "create",
  editingEventId: null,
  currentEvent: null,
  currentResult: null,
  currentView: "home",
  lastMainView: "home",
};

const elements = {
  topLeftButton: document.getElementById("top-left-button"),
  topRightButton: document.getElementById("top-right-button"),
  topbarTitle: document.getElementById("topbar-title"),
  toast: document.getElementById("toast"),

  homeCreateCard: document.getElementById("home-create-card"),
  homeEvents: document.getElementById("home-events"),
  homeReceipts: document.getElementById("home-receipts"),

  createForm: document.getElementById("create-event-form"),
  createSubmitButton: document.getElementById("create-event-submit"),
  eventTitleInput: document.getElementById("event-title"),
  eventDateInput: document.getElementById("event-date"),
  createParticipants: document.getElementById("create-participants"),
  addParticipantContact: document.getElementById("add-participant-contact"),
  addParticipantGroup: document.getElementById("add-participant-group"),
  addParticipantManual: document.getElementById("add-participant-manual"),

  eventsList: document.getElementById("events-list"),

  eventTitleText: document.getElementById("event-title-text"),
  eventSubtitle: document.getElementById("event-subtitle"),
  summaryTotal: document.getElementById("summary-total"),
  summarySelected: document.getElementById("summary-selected"),
  summaryPerPerson: document.getElementById("summary-per-person"),
  itemsHelper: document.getElementById("items-helper"),
  eventItems: document.getElementById("event-items"),
  eventEditButton: document.getElementById("event-edit-button"),
  manualItemForm: document.getElementById("manual-item-form"),
  manualItemName: document.getElementById("manual-item-name"),
  manualItemAmount: document.getElementById("manual-item-amount"),
  uploadReceiptButton: document.getElementById("upload-receipt-button"),
  receiptFileInput: document.getElementById("receipt-file-input"),
  calculateButton: document.getElementById("calculate-button"),

  resultList: document.getElementById("result-list"),
  shareResultButton: document.getElementById("share-result-button"),

  checksList: document.getElementById("checks-list"),

  profileAvatar: document.getElementById("profile-avatar"),
  profileName: document.getElementById("profile-name"),
  profileUsername: document.getElementById("profile-username"),
  profileEditName: document.getElementById("profile-edit-name"),
  statEvents: document.getElementById("stat-events"),
  statParticipants: document.getElementById("stat-participants"),
  statTotal: document.getElementById("stat-total"),

  contactsModal: document.getElementById("contacts-modal"),
  contactsList: document.getElementById("contacts-list"),
  closeContactsModal: document.getElementById("close-contacts-modal"),
  requestContactsButton: document.getElementById("request-contacts-button"),

  groupsModal: document.getElementById("groups-modal"),
  groupsList: document.getElementById("groups-list"),
  closeGroupsModal: document.getElementById("close-groups-modal"),

  bottomPlus: document.getElementById("bottom-plus"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toNumber(value) {
  const normalized = String(value ?? "0").replace(",", ".");
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value) {
  const amount = toNumber(value);
  const isInteger = Math.abs(amount - Math.round(amount)) < 0.00001;
  const options = isInteger
    ? { maximumFractionDigits: 0 }
    : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  return `${amount.toLocaleString("ru-RU", options)} ₽`;
}

function formatDate(value) {
  if (!value) {
    return "Без даты";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: parsed.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
  });
}

function getInitials(name) {
  const normalized = String(name || "?").trim();
  if (!normalized) {
    return "?";
  }

  const parts = normalized.split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() || "").join("");
}

function showToast(message, duration = 2400) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("is-hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.add("is-hidden");
  }, duration);
}

async function api(path, options = {}) {
  const requestOptions = { ...options };
  const headers = new Headers(requestOptions.headers || {});

  if (telegram?.initData) {
    headers.set("X-Telegram-Init-Data", telegram.initData);
  }

  const hasFormDataBody = requestOptions.body instanceof FormData;
  if (!hasFormDataBody && requestOptions.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  requestOptions.headers = headers;

  const response = await fetch(path, requestOptions);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = data?.detail || data?.message || `Ошибка ${response.status}`;
    throw new Error(error);
  }
  return data;
}

async function apiJson(path, method, payload = {}) {
  return api(path, {
    method,
    body: JSON.stringify(payload),
  });
}

function getParticipantLabel(participant) {
  return participant.display_name || participant.username || "Участник";
}

function isRootView(view) {
  return ["home", "events", "checks", "profile"].includes(view);
}

function openView(view) {
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-visible", section.id === `view-${view}`);
  });

  state.currentView = view;
  if (isRootView(view)) {
    state.lastMainView = view;
  }

  document.querySelectorAll(".bottom-nav .nav-item[data-nav]").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.nav === view);
  });

  updateTopbar();
}

function updateTopbar() {
  const view = state.currentView;

  if (view === "event" && state.currentEvent?.event?.title) {
    elements.topbarTitle.textContent = state.currentEvent.event.title;
  } else if (view === "result") {
    elements.topbarTitle.textContent = "Результат";
  } else if (view === "create") {
    elements.topbarTitle.textContent = state.createMode === "edit" ? "Изменить событие" : "Новое событие";
  } else if (view === "events") {
    elements.topbarTitle.textContent = "События";
  } else if (view === "checks") {
    elements.topbarTitle.textContent = "Чеки";
  } else if (view === "profile") {
    elements.topbarTitle.textContent = "Профиль";
  } else {
    elements.topbarTitle.textContent = "SplitCheck";
  }

  elements.topLeftButton.textContent = isRootView(view) ? "Закрыть" : "Назад";
}

function renderEmpty(container, text) {
  container.innerHTML = `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function renderHome() {
  const events = state.dashboard.events || [];
  const receipts = state.dashboard.receipts || [];

  if (!events.length) {
    renderEmpty(elements.homeEvents, "Пока нет событий. Нажмите «Создать событие».");
  } else {
    elements.homeEvents.innerHTML = events
      .map(
        (event) => `
          <article class="event-card" data-event-id="${event.id}">
            <div>
              <div class="event-card-title">${escapeHtml(event.title)}</div>
              <div class="event-card-meta">${event.participants_count} участников • ${formatDate(event.event_date || event.created_at)}</div>
            </div>
            <div class="event-card-amount">${formatMoney(event.per_person_amount)}</div>
          </article>
        `,
      )
      .join("");
  }

  if (!receipts.length) {
    renderEmpty(elements.homeReceipts, "Загрузите первый чек в событие.");
  } else {
    elements.homeReceipts.innerHTML = receipts
      .map(
        (receipt) => `
          <article class="receipt-card" data-event-id="${receipt.event_id}">
            <div>
              <div class="receipt-card-title">${escapeHtml(receipt.store_name)}</div>
              <div class="receipt-card-meta">${formatDate(receipt.created_at)} • ${escapeHtml(receipt.event_title)}</div>
            </div>
            <div class="receipt-card-amount">${formatMoney(receipt.total_amount)}</div>
          </article>
        `,
      )
      .join("");
  }
}

function renderEvents() {
  const events = state.events || [];

  if (!events.length) {
    renderEmpty(elements.eventsList, "Событий пока нет. Создайте первое событие.");
    return;
  }

  elements.eventsList.innerHTML = events
    .map(
      (event) => `
        <article class="event-card" data-event-id="${event.id}">
          <div>
            <div class="event-card-title">${escapeHtml(event.title)}</div>
            <div class="event-card-meta">${event.participants_count} участников • ${formatDate(event.event_date || event.created_at)}</div>
          </div>
          <div class="event-card-amount">${formatMoney(event.total_amount)}</div>
        </article>
      `,
    )
    .join("");
}

function renderChecks() {
  const receipts = state.recentReceipts || [];
  if (!receipts.length) {
    renderEmpty(elements.checksList, "Пока нет чеков.");
    return;
  }

  elements.checksList.innerHTML = receipts
    .map(
      (receipt) => `
        <article class="receipt-card" data-event-id="${receipt.event_id}">
          <div>
            <div class="receipt-card-title">${escapeHtml(receipt.store_name)}</div>
            <div class="receipt-card-meta">${formatDate(receipt.created_at)} • ${escapeHtml(receipt.event_title)}</div>
          </div>
          <div class="receipt-card-amount">${formatMoney(receipt.total_amount)}</div>
        </article>
      `,
    )
    .join("");
}

function renderProfile() {
  const profile = state.me?.profile;
  const stats = state.stats || state.me?.stats || {};

  if (!profile) {
    return;
  }

  const telegramUsername = profile.username ? `@${profile.username}` : "";
  const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(" ").trim();
  const visibleName = profile.display_name || profile.custom_name || fullName || telegramUsername || "Профиль";
  elements.profileName.textContent = visibleName;
  elements.profileUsername.textContent = telegramUsername || "без username";
  elements.profileAvatar.textContent = getInitials(visibleName);

  elements.statEvents.textContent = String(stats.events_count || 0);
  elements.statParticipants.textContent = String(stats.participants_count || 0);
  elements.statTotal.textContent = formatMoney(stats.total_split_amount || 0);
}

function resetCreateDraft() {
  state.createMode = "create";
  state.editingEventId = null;

  const profile = state.me?.profile;
  if (!profile) {
    state.createParticipants = [];
    return;
  }

  state.createParticipants = [
    {
      local_id: "owner",
      user_id: profile.user_id,
      display_name: profile.display_name,
      username: profile.username,
      is_owner: true,
    },
  ];

  elements.eventTitleInput.value = "";
  elements.eventDateInput.value = "";
  elements.createSubmitButton.textContent = "Создать событие";
  renderCreateParticipants();
}

function openCreateForNew() {
  resetCreateDraft();
  openView("create");
}

function openCreateForEdit() {
  if (!state.currentEvent?.event) {
    showToast("Событие не загружено.");
    return;
  }

  const detail = state.currentEvent;
  const participants = detail.participants || [];

  state.createMode = "edit";
  state.editingEventId = detail.event.id;
  state.createParticipants = participants.map((participant) => ({
    local_id: participant.user_id ? `participant-${participant.user_id}` : `member-${participant.id}`,
    user_id: participant.user_id || null,
    display_name: participant.display_name,
    username: participant.username || null,
    phone: participant.phone || null,
    is_owner: Boolean(participant.is_owner),
  }));

  elements.eventTitleInput.value = detail.event.title || "";
  elements.eventDateInput.value = detail.event.event_date || "";
  elements.createSubmitButton.textContent = "Сохранить изменения";
  renderCreateParticipants();
  openView("create");
}

function renderCreateParticipants() {
  if (!state.createParticipants.length) {
    renderEmpty(elements.createParticipants, "Добавьте участников.");
    return;
  }

  elements.createParticipants.innerHTML = state.createParticipants
    .map((participant, index) => {
      const label = getParticipantLabel(participant);
      return `
        <div class="participant-row">
          <div class="participant-left">
            <div class="participant-badge">${escapeHtml(getInitials(label))}</div>
            <div>
              <div class="event-card-title">${escapeHtml(label)}</div>
              <div class="event-card-meta">${participant.is_owner ? "Организатор" : participant.username ? `@${escapeHtml(participant.username)}` : "Участник"}</div>
            </div>
          </div>
          ${participant.is_owner ? "" : `<button type="button" class="participant-remove" data-remove-index="${index}">−</button>`}
        </div>
      `;
    })
    .join("");
}

function openContactsModal() {
  renderContacts();
  elements.contactsModal.classList.remove("is-hidden");
}

function closeContactsModal() {
  elements.contactsModal.classList.add("is-hidden");
}

function renderContacts() {
  elements.requestContactsButton.disabled = !(
    telegram?.sendData ||
    state.contactsRequestLink ||
    state.contactsRequestTgLink
  );

  if (!state.contacts.length) {
    renderEmpty(
      elements.contactsList,
      "Контактов пока нет. Нажмите кнопку выше, выберите людей в Telegram и вернитесь в Mini App.",
    );
    return;
  }

  elements.contactsList.innerHTML = state.contacts
    .map((contact) => {
      const alreadyAdded = state.createParticipants.some(
        (participant) => participant.user_id && participant.user_id === contact.user_id,
      );
      return `
        <div class="contact-row">
          <div>
            <div class="event-card-title">${escapeHtml(contact.display_name || contact.first_name || "Контакт")}</div>
            <div class="event-card-meta">${contact.username ? `@${escapeHtml(contact.username)}` : "Telegram контакт"}</div>
          </div>
          <button type="button" class="contact-add" data-contact-id="${contact.user_id}" ${alreadyAdded ? "disabled" : ""}>
            ${alreadyAdded ? "Добавлен" : "Добавить"}
          </button>
        </div>
      `;
    })
    .join("");
}

function closeGroupsModal() {
  elements.groupsModal.classList.add("is-hidden");
}

function renderGroups() {
  if (!state.groups.length) {
    renderEmpty(
      elements.groupsList,
      "Нет доступных групп. Добавьте бота в групповой чат и попросите участников отправить /join.",
    );
    return;
  }

  elements.groupsList.innerHTML = state.groups
    .map(
      (group) => `
        <div class="contact-row">
          <div>
            <div class="event-card-title">${escapeHtml(group.title)}</div>
            <div class="event-card-meta">${group.participants_count} участников замечено</div>
          </div>
          <button type="button" class="contact-add" data-group-chat-id="${group.chat_id}">
            Импорт
          </button>
        </div>
      `,
    )
    .join("");
}

async function openGroupsModal() {
  try {
    const response = await api("/api/groups");
    state.groups = response.groups || [];
    renderGroups();
    elements.groupsModal.classList.remove("is-hidden");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось получить список групп.");
  }
}

function addParticipantFromContact(contactId) {
  const contact = state.contacts.find((candidate) => Number(candidate.user_id) === Number(contactId));
  if (!contact) {
    return;
  }

  const exists = state.createParticipants.some(
    (participant) => participant.user_id && Number(participant.user_id) === Number(contact.user_id),
  );
  if (exists) {
    showToast("Этот участник уже добавлен.");
    return;
  }

  state.createParticipants.push({
    local_id: `contact-${contact.user_id}`,
    user_id: contact.user_id,
    display_name: contact.display_name,
    username: contact.username,
    phone: contact.phone,
    is_owner: false,
  });

  renderCreateParticipants();
  renderContacts();
}

function addParticipantToDraft(participant) {
  if (!participant) {
    return;
  }

  const exists = state.createParticipants.some(
    (candidate) =>
      candidate.user_id &&
      participant.user_id &&
      Number(candidate.user_id) === Number(participant.user_id),
  );
  if (exists) {
    return;
  }

  state.createParticipants.push({
    local_id: participant.user_id
      ? `participant-${participant.user_id}`
      : `manual-${Date.now()}-${Math.random()}`,
    user_id: participant.user_id || null,
    display_name: participant.display_name,
    username: participant.username || null,
    phone: participant.phone || null,
    is_owner: false,
  });
}

async function importGroupParticipants(chatId) {
  try {
    const response = await api(`/api/groups/${chatId}/participants`);
    const participants = response.participants || [];
    let added = 0;
    participants.forEach((participant) => {
      const before = state.createParticipants.length;
      addParticipantToDraft(participant);
      if (state.createParticipants.length > before) {
        added += 1;
      }
    });
    renderCreateParticipants();
    closeGroupsModal();
    showToast(added > 0 ? `Импортировано участников: ${added}.` : "Новых участников не найдено.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось импортировать участников группы.");
  }
}

function requestContactsViaTelegram() {
  const canSendData = Boolean(telegram?.sendData && telegram?.initDataUnsafe?.query_id);
  if (canSendData) {
    try {
      showToast("Отправил запрос в чат с ботом.");
      telegram.sendData(
        JSON.stringify({
          action: "request_contacts",
          source: "mini_app",
        }),
      );
      return;
    } catch {
      // sendData может быть недоступен для текущего способа открытия Mini App.
    }
  }

  if (telegram?.showAlert) {
    telegram.showAlert("Сейчас откроется чат с ботом. Нажмите Start, затем выберите контакты.");
  }

  if (telegram?.openTelegramLink && state.contactsRequestLink) {
    telegram.openTelegramLink(state.contactsRequestLink);
    return;
  }

  if (telegram?.openLink && state.contactsRequestTgLink) {
    telegram.openLink(state.contactsRequestTgLink);
    return;
  }

  if (state.contactsRequestLink) {
    window.open(state.contactsRequestLink, "_blank", "noopener,noreferrer");
    return;
  }

  showToast("Ссылка на бота недоступна.");
}

function addManualParticipant() {
  const name = window.prompt("Введите имя участника");
  if (!name) {
    return;
  }

  const normalized = name.trim();
  if (!normalized) {
    return;
  }

  state.createParticipants.push({
    local_id: `manual-${Date.now()}-${Math.random()}`,
    user_id: null,
    display_name: normalized,
    username: null,
    phone: null,
    is_owner: false,
  });

  renderCreateParticipants();
}

function findItemById(itemId) {
  const items = state.currentEvent?.items || [];
  return items.find((item) => Number(item.id) === Number(itemId)) || null;
}

function renderCurrentEvent() {
  const detail = state.currentEvent;
  if (!detail) {
    elements.eventItems.innerHTML = "";
    return;
  }

  const event = detail.event;
  const participants = detail.participants || [];
  const summary = detail.summary || {};
  const items = detail.items || [];
  const canAssign = Boolean(detail.permissions?.is_admin);
  const canEditEvent = Boolean(detail.permissions?.is_admin);

  elements.eventTitleText.textContent = event.title;
  elements.eventSubtitle.textContent = `${participants.length} участников • ${formatDate(event.event_date || event.created_at)}`;
  elements.eventEditButton.style.display = canEditEvent ? "" : "none";
  elements.summaryTotal.textContent = formatMoney(summary.total_amount || 0);
  elements.summarySelected.textContent = formatMoney(summary.selected_amount || 0);
  elements.summaryPerPerson.textContent = formatMoney(summary.per_person_amount || 0);
  elements.itemsHelper.textContent = canAssign
    ? "Админ может назначать любых участников"
    : "Отмечайте позиции, которые брали вы";

  if (!items.length) {
    renderEmpty(elements.eventItems, "Пока нет позиций. Загрузите чек.");
    return;
  }

  elements.eventItems.innerHTML = items
    .map((item) => {
      const assignedIds = new Set(item.assigned_member_ids || []);
      const chips = participants
        .map((participant) => {
          const active = assignedIds.has(participant.id);
          const clickable = canAssign;
          return `
            <button
              type="button"
              class="member-chip ${active ? "active" : ""} ${clickable ? "clickable" : ""}"
              data-item-id="${item.id}"
              data-member-id="${participant.id}"
              ${clickable ? "" : "disabled"}
            >
              ${escapeHtml(getInitials(participant.display_name))}
            </button>
          `;
        })
        .join("");

      return `
        <article class="item-card">
          <div class="item-top">
            <div class="item-main">
              <input class="item-mine-checkbox" type="checkbox" data-item-id="${item.id}" ${item.is_mine ? "checked" : ""}>
              <div>
                <div class="item-name">${escapeHtml(item.name)}</div>
                <div class="item-meta">${escapeHtml(item.store_name)} • x${escapeHtml(String(item.quantity))}</div>
              </div>
            </div>
            <div class="item-price">${formatMoney(item.sum)}</div>
          </div>
          <div class="item-participants">${chips}</div>
        </article>
      `;
    })
    .join("");
}

function renderResult() {
  const result = state.currentResult;
  if (!result) {
    renderEmpty(elements.resultList, "Сначала посчитайте событие.");
    return;
  }

  const participants = result.participants || [];
  if (!participants.length) {
    renderEmpty(elements.resultList, "Нет участников для расчёта.");
    return;
  }

  elements.resultList.innerHTML = participants
    .map(
      (participant) => `
        <article class="result-card">
          <div>
            <div class="event-card-title">${escapeHtml(participant.display_name)}</div>
            <div class="event-card-meta">${participant.is_owner ? "Организатор" : "Участник"}</div>
          </div>
          <div class="result-card-amount">${formatMoney(participant.amount)}</div>
        </article>
      `,
    )
    .join("");
}

async function refreshBaseData() {
  const [meResponse, dashboardResponse, eventsResponse, contactsResponse, receiptsResponse] = await Promise.all([
    api("/api/me"),
    api("/api/dashboard"),
    api("/api/events"),
    api("/api/contacts"),
    api("/api/receipts/recent?limit=50"),
  ]);

  state.me = meResponse;
  state.stats = meResponse.stats || dashboardResponse.stats;
  state.dashboard = dashboardResponse.dashboard || { events: [], receipts: [] };
  state.events = eventsResponse.events || [];
  state.contacts = contactsResponse.contacts || [];
  state.contactsRequestLink = contactsResponse.request_contacts_link || null;
  state.contactsRequestTgLink = contactsResponse.request_contacts_tg_link || null;
  state.recentReceipts = receiptsResponse.receipts || [];
}

async function openEvent(eventId) {
  const detail = await api(`/api/events/${eventId}`);
  state.currentEvent = detail;
  renderCurrentEvent();
  openView("event");
}

async function handleCreateEventSubmit(event) {
  event.preventDefault();

  const title = elements.eventTitleInput.value.trim();
  if (!title) {
    showToast("Введите название события.");
    return;
  }

  const participants = state.createParticipants
    .filter((participant) => !participant.is_owner)
    .map((participant) => ({
      user_id: participant.user_id,
      display_name: participant.display_name,
      username: participant.username,
      phone: participant.phone,
    }));

  elements.createSubmitButton.disabled = true;

  try {
    const payload = {
      title,
      event_date: elements.eventDateInput.value || null,
      participants,
    };

    let response;
    if (state.createMode === "edit" && state.editingEventId) {
      response = await apiJson(`/api/events/${state.editingEventId}`, "PUT", payload);
    } else {
      response = await apiJson("/api/events", "POST", payload);
    }

    await refreshBaseData();
    renderHome();
    renderEvents();
    renderChecks();
    renderProfile();
    const responseEventId = response?.event?.event?.id;

    if (state.createMode === "edit") {
      showToast("Событие обновлено.");
      if (responseEventId) {
        await openEvent(responseEventId);
      } else {
        openView("events");
      }
    } else {
      resetCreateDraft();
      showToast("Событие создано.");
      if (responseEventId) {
        await openEvent(responseEventId);
      } else {
        openView("events");
      }
    }
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Ошибка создания события.");
  } finally {
    elements.createSubmitButton.disabled = false;
  }
}

async function handleToggleMine(itemId) {
  if (!state.currentEvent?.event?.id) {
    return;
  }

  try {
    const response = await api(`/api/events/${state.currentEvent.event.id}/items/${itemId}/toggle-mine`, {
      method: "POST",
    });
    state.currentEvent = response.event;
    renderCurrentEvent();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось обновить выбор позиции.");
  }
}

async function handleAdminAssign(itemId, memberId) {
  if (!state.currentEvent?.event?.id) {
    return;
  }

  const item = findItemById(itemId);
  const assignedNow = item?.assigned_member_ids?.includes(Number(memberId));

  try {
    const response = await apiJson(
      `/api/events/${state.currentEvent.event.id}/items/${itemId}/assign`,
      "POST",
      {
        member_id: Number(memberId),
        assigned: !assignedNow,
      },
    );
    state.currentEvent = response.event;
    renderCurrentEvent();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось назначить участника.");
  }
}

async function handleUploadReceipt(file) {
  if (!file || !state.currentEvent?.event?.id) {
    return;
  }

  const formData = new FormData();
  formData.append("receipt_photo", file);
  if (telegram?.initData) {
    formData.append("init_data", telegram.initData);
  }

  elements.uploadReceiptButton.disabled = true;
  elements.uploadReceiptButton.textContent = "Загрузка...";

  try {
    const response = await api(`/api/events/${state.currentEvent.event.id}/receipts/upload`, {
      method: "POST",
      body: formData,
    });

    state.currentEvent = response.event;
    await refreshBaseData();

    renderCurrentEvent();
    renderHome();
    renderEvents();
    renderChecks();
    renderProfile();
    showToast("Чек обработан и добавлен в событие.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось загрузить чек.");
  } finally {
    elements.uploadReceiptButton.disabled = false;
    elements.uploadReceiptButton.textContent = "Загрузить чек";
    elements.receiptFileInput.value = "";
  }
}

async function handleManualItemSubmit(event) {
  event.preventDefault();
  if (!state.currentEvent?.event?.id) {
    return;
  }

  const name = elements.manualItemName.value.trim();
  const amount = elements.manualItemAmount.value.trim();

  if (!name || !amount) {
    showToast("Введите название и стоимость позиции.");
    return;
  }

  try {
    const response = await apiJson(
      `/api/events/${state.currentEvent.event.id}/items/manual`,
      "POST",
      { name, amount },
    );
    state.currentEvent = response.event;
    renderCurrentEvent();
    await refreshBaseData();
    renderHome();
    renderEvents();
    renderChecks();
    renderProfile();
    elements.manualItemForm.reset();
    showToast("Позиция добавлена.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось добавить позицию.");
  }
}

async function handleProfileNameEdit() {
  const currentProfile = state.me?.profile;
  const currentName = currentProfile?.custom_name || currentProfile?.display_name || "";
  const nextNameRaw = window.prompt("Введите имя, которое будет видно в событиях", currentName);
  if (nextNameRaw === null) {
    return;
  }
  const customName = nextNameRaw.trim();

  try {
    const response = await apiJson("/api/me/name", "POST", {
      custom_name: customName || null,
    });
    state.me = {
      profile: response.profile,
      stats: response.stats,
    };
    state.stats = response.stats;
    renderProfile();
    await refreshBaseData();
    renderHome();
    renderEvents();
    renderChecks();
    showToast(customName ? "Имя сохранено." : "Имя сброшено на Telegram-имя.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось сохранить имя.");
  }
}

async function handleCalculate() {
  if (!state.currentEvent?.event?.id) {
    return;
  }

  elements.calculateButton.disabled = true;
  try {
    const response = await api(`/api/events/${state.currentEvent.event.id}/calculate`, {
      method: "POST",
    });
    state.currentResult = response.result;
    renderResult();
    openView("result");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось выполнить расчёт.");
  } finally {
    elements.calculateButton.disabled = false;
  }
}

async function handleShareResult() {
  if (!state.currentResult) {
    showToast("Сначала рассчитайте событие.");
    return;
  }

  const lines = [
    `Результат: ${state.currentResult.event.title}`,
    ...state.currentResult.participants.map(
      (participant) => `${participant.display_name}: ${formatMoney(participant.amount)}`,
    ),
  ];
  const text = lines.join("\n");

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      showToast("Результат скопирован в буфер обмена.");
      return;
    }
  } catch {
    // noop
  }

  if (telegram?.showPopup) {
    telegram.showPopup({
      title: "Результат",
      message: text,
      buttons: [{ type: "ok", text: "Ок" }],
    });
  } else {
    showToast("Не удалось скопировать результат автоматически.");
  }
}

function bindEvents() {
  elements.topLeftButton.addEventListener("click", () => {
    if (isRootView(state.currentView)) {
      if (telegram?.close) {
        telegram.close();
      }
      return;
    }

    if (state.currentView === "create" && state.createMode === "edit") {
      openView("event");
      return;
    }

    if (state.currentView === "result") {
      openView("event");
      return;
    }

    if (state.currentView === "event") {
      openView("events");
      return;
    }

    openView(state.lastMainView || "home");
  });

  elements.topRightButton.addEventListener("click", async () => {
    try {
      await refreshBaseData();
      renderHome();
      renderEvents();
      renderChecks();
      renderProfile();
      if (state.currentEvent) {
        const refreshed = await api(`/api/events/${state.currentEvent.event.id}`);
        state.currentEvent = refreshed;
        renderCurrentEvent();
      }
      showToast("Данные обновлены.");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Ошибка обновления.");
    }
  });

  elements.homeCreateCard.addEventListener("click", openCreateForNew);

  document.querySelectorAll("[data-open-view]").forEach((button) => {
    button.addEventListener("click", () => openView(button.dataset.openView));
  });

  document.querySelectorAll(".bottom-nav .nav-item[data-nav]").forEach((button) => {
    button.addEventListener("click", () => openView(button.dataset.nav));
  });

  elements.bottomPlus.addEventListener("click", openCreateForNew);

  elements.createForm.addEventListener("submit", handleCreateEventSubmit);

  elements.createParticipants.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const removeIndex = target.dataset.removeIndex;
    if (!removeIndex) {
      return;
    }

    state.createParticipants.splice(Number(removeIndex), 1);
    renderCreateParticipants();
  });

  elements.addParticipantContact.addEventListener("click", openContactsModal);
  elements.addParticipantGroup.addEventListener("click", openGroupsModal);
  elements.addParticipantManual.addEventListener("click", addManualParticipant);
  elements.requestContactsButton.addEventListener("click", requestContactsViaTelegram);

  elements.closeContactsModal.addEventListener("click", closeContactsModal);
  elements.contactsModal.addEventListener("click", (event) => {
    if (event.target === elements.contactsModal) {
      closeContactsModal();
      return;
    }

    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const contactId = target.dataset.contactId;
    if (contactId) {
      addParticipantFromContact(contactId);
    }
  });

  elements.closeGroupsModal.addEventListener("click", closeGroupsModal);
  elements.groupsModal.addEventListener("click", (event) => {
    if (event.target === elements.groupsModal) {
      closeGroupsModal();
      return;
    }

    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const chatId = target.dataset.groupChatId;
    if (chatId) {
      importGroupParticipants(Number(chatId));
    }
  });

  const eventCardHandler = async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const card = target.closest("[data-event-id]");
    if (!card) {
      return;
    }

    const eventId = Number(card.dataset.eventId);
    if (!Number.isFinite(eventId)) {
      return;
    }

    try {
      await openEvent(eventId);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Не удалось открыть событие.");
    }
  };

  elements.homeEvents.addEventListener("click", eventCardHandler);
  elements.eventsList.addEventListener("click", eventCardHandler);
  elements.homeReceipts.addEventListener("click", eventCardHandler);
  elements.checksList.addEventListener("click", eventCardHandler);

  elements.uploadReceiptButton.addEventListener("click", () => {
    elements.receiptFileInput.click();
  });

  elements.receiptFileInput.addEventListener("change", () => {
    const file = elements.receiptFileInput.files?.[0];
    if (file) {
      handleUploadReceipt(file);
    }
  });

  elements.eventItems.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (!target.classList.contains("item-mine-checkbox")) {
      return;
    }

    const itemId = Number(target.dataset.itemId);
    if (Number.isFinite(itemId)) {
      handleToggleMine(itemId);
    }
  });

  elements.eventItems.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const chip = target.closest(".member-chip");
    if (!(chip instanceof HTMLElement)) {
      return;
    }

    if (!state.currentEvent?.permissions?.is_admin) {
      return;
    }

    const itemId = Number(chip.dataset.itemId);
    const memberId = Number(chip.dataset.memberId);
    if (Number.isFinite(itemId) && Number.isFinite(memberId)) {
      handleAdminAssign(itemId, memberId);
    }
  });

  elements.manualItemForm.addEventListener("submit", handleManualItemSubmit);
  elements.calculateButton.addEventListener("click", handleCalculate);
  elements.shareResultButton.addEventListener("click", handleShareResult);
  elements.profileEditName.addEventListener("click", handleProfileNameEdit);
  elements.eventEditButton.addEventListener("click", openCreateForEdit);
}

async function init() {
  if (telegram) {
    telegram.ready();
    telegram.expand();
  }

  bindEvents();

  try {
    await refreshBaseData();
    renderHome();
    renderEvents();
    renderChecks();
    renderProfile();
    resetCreateDraft();
    openView("home");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Не удалось загрузить данные.");
  }
}

document.addEventListener("DOMContentLoaded", init);
