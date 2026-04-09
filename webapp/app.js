const webApp = window.Telegram?.WebApp;
let previewUrl = null;

const elements = {
  form: document.getElementById("receipt-form"),
  receiptFile: document.getElementById("receipt-file"),
  submitButton: document.getElementById("submit-button"),
  statusBanner: document.getElementById("status-banner"),
  userName: document.getElementById("user-name"),
  launchMode: document.getElementById("launch-mode"),
  previewCard: document.getElementById("preview-card"),
  previewImage: document.getElementById("preview-image"),
  previewName: document.getElementById("preview-name"),
  previewSize: document.getElementById("preview-size"),
  resultCard: document.getElementById("result-card"),
  receiptTimestamp: document.getElementById("receipt-timestamp"),
  receiptTotal: document.getElementById("receipt-total"),
  receiptFn: document.getElementById("receipt-fn"),
  receiptDoc: document.getElementById("receipt-doc"),
  qrRaw: document.getElementById("qr-raw"),
};

function setStatus(message, type = "info") {
  elements.statusBanner.textContent = message;
  elements.statusBanner.className = "status-banner";
  if (type !== "info") {
    elements.statusBanner.classList.add(type);
  }
}

function getDisplayName(user) {
  if (!user) {
    return "Недоступно";
  }

  if (user.username) {
    return `@${user.username}`;
  }

  const name = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  return name || `id ${user.id}`;
}

function applyTelegramTheme() {
  if (!webApp?.themeParams) {
    return;
  }

  const root = document.documentElement;
  const { bg_color, text_color, hint_color, button_color } = webApp.themeParams;

  if (bg_color) {
    root.style.setProperty("--bg", bg_color);
  }
  if (text_color) {
    root.style.setProperty("--text", text_color);
  }
  if (hint_color) {
    root.style.setProperty("--muted", hint_color);
  }
  if (button_color) {
    root.style.setProperty("--accent", button_color);
  }
}

function updateUiState() {
  const user = webApp?.initDataUnsafe?.user;
  elements.userName.textContent = getDisplayName(user);
  elements.launchMode.textContent = webApp ? "Telegram Mini App" : "Обычный браузер";
}

function formatFileSize(sizeInBytes) {
  return `${(sizeInBytes / (1024 * 1024)).toFixed(2)} МБ`;
}

function updatePreview(file) {
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }

  if (!file) {
    elements.previewCard.classList.add("is-hidden");
    elements.previewImage.removeAttribute("src");
    elements.previewName.textContent = "Файл не выбран";
    elements.previewSize.textContent = "0 МБ";
    return;
  }

  previewUrl = URL.createObjectURL(file);
  elements.previewImage.src = previewUrl;
  elements.previewName.textContent = file.name;
  elements.previewSize.textContent = formatFileSize(file.size);
  elements.previewCard.classList.remove("is-hidden");
}

function fillResult(receipt, qrPayload) {
  elements.resultCard.classList.remove("is-hidden");
  const safeReceipt = receipt || {};
  elements.receiptTimestamp.textContent = safeReceipt.timestamp || "Не удалось определить";
  elements.receiptTotal.textContent = safeReceipt.total_amount
    ? `${safeReceipt.total_amount} ₽`
    : "Не удалось определить";
  elements.receiptFn.textContent = safeReceipt.fiscal_drive_number || "Не найден";
  elements.receiptDoc.textContent = safeReceipt.fiscal_document_number && safeReceipt.fiscal_sign
    ? `${safeReceipt.fiscal_document_number} / ${safeReceipt.fiscal_sign}`
    : "Не найден";
  elements.qrRaw.textContent = qrPayload || "Не найден";
}

async function submitViaBackend(file) {
  const formData = new FormData();
  formData.append("receipt_photo", file);
  if (webApp?.initData) {
    formData.append("init_data", webApp.initData);
  }

  const response = await fetch("/api/receipts/process-photo", {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Backend не смог обработать данные.");
  }

  return data;
}

async function handleSubmit(event) {
  event.preventDefault();

  const file = elements.receiptFile.files?.[0];
  if (!file) {
    setStatus("Сначала выберите фотографию чека.", "warning");
    return;
  }

  elements.submitButton.disabled = true;
  setStatus("Ищем QR-код на фотографии...", "info");

  try {
    const result = await submitViaBackend(file);
    fillResult(result.receipt, result.qr_payload);

    if (webApp?.HapticFeedback) {
      webApp.HapticFeedback.notificationOccurred("success");
    }
    if (result.telegram_delivery === "sent" && webApp?.MainButton) {
      webApp.MainButton.setText("Закрыть");
      webApp.MainButton.show();
    } else if (webApp?.MainButton) {
      webApp.MainButton.hide();
    }
    setStatus(result.message || "Чек обработан.", "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Произошла неизвестная ошибка.";
    setStatus(message, "error");
  } finally {
    elements.submitButton.disabled = false;
  }
}

function init() {
  if (webApp) {
    webApp.ready();
    webApp.expand();
    applyTelegramTheme();
    if (webApp.MainButton) {
      webApp.MainButton.onClick(() => webApp.close());
      webApp.MainButton.hide();
    }
    setStatus("Mini App готов. Загрузите фото чека для обработки.", "success");
  } else {
    setStatus(
      "Страница открыта вне Telegram. Фото можно проверить и в браузере, но сообщение в чат бот отправит только внутри Telegram.",
      "warning",
    );
  }

  updateUiState();
  elements.receiptFile.addEventListener("change", () => {
    updatePreview(elements.receiptFile.files?.[0] || null);
  });
  elements.form.addEventListener("submit", handleSubmit);
}

document.addEventListener("DOMContentLoaded", init);
