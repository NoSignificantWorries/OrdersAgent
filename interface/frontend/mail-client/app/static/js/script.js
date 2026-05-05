// ===== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====
let emails = [];
let selectedEmailId = null;

// ===== КОНФИГУРАЦИЯ СТАТУСОВ =====
const statusConfig = {
    waiting: { name: "Ожидание" },
    processing: { name: "Обработка" },
    clarification: { name: "Класс определён" },
    review: { name: "Требуется выбор класса" },
    completed: { name: "Выполнена" }
};

// варианты решения модели / класса письма
const decisionOptions = [
    { value: "",        label: "Выберите класс" },
    { value: "auto_0",  label: "Заявка" },
    { value: "auto_1",  label: "Расчёт" },
    { value: "review",  label: "Требуется ручной выбор" },
];

// Кэш для материалов чата
let cachedMaterials = null;

// ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
function formatDate(dateString) {
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return "";
    const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    return `${date.getDate()} ${months[date.getMonth()]}`;
}

function formatDateTime(dateString) {
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("ru-RU");
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? "";
    return div.innerHTML;
}

function showLoading() {
    const emailView = document.getElementById('emailView');
    if (emailView) {
        emailView.innerHTML = `
            <div class="email-loading-wrapper">
                <div class="loading"></div>
            </div>
        `;
    }
}

function highlightSelectedEmail(id) {
    document.querySelectorAll('.email-item').forEach(item => {
        item.classList.remove('selected');
    });
    const selectedItem = document.querySelector(`.email-item[data-id="${id}"]`);
    if (selectedItem) {
        selectedItem.classList.add('selected');
    }
}

function applyEmailUpdatesToOpenView(email) {
    if (!email) return;
    const currentStatus = statusConfig[email.status] || statusConfig.waiting;
    const statusDisplay = document.querySelector('.status-display');
    if (statusDisplay) {
        statusDisplay.textContent = currentStatus.name;
        statusDisplay.className = `status-display status-${email.status}`;
    }
    const decisionSelect = document.getElementById('decision-select');
    if (decisionSelect) {
        const newValue = email.model_decision || "";
        if (decisionSelect.value !== newValue) {
            decisionSelect.value = newValue;
        }
    }
}

function mapStatus(status) {
    if (!status) return "waiting";
    const s = status.toLowerCase();
    if (s === "wait" || s === "waiting") return "waiting";
    if (s === "classified" || s === "clarification") return "clarification";
    if (s === "review") return "review";
    if (s === "processing") return "processing";
    if (s === "done" || s === "completed") return "completed";
    return "waiting";
}

// ===== ЗАГРУЗКА ПИСЕМ ИЗ API =====
async function loadEmailsFromApi(showLoadingState = true) {
    const listEl = document.getElementById("emailsContainer");
    const viewEl = document.getElementById("emailView");
    const countEl = document.querySelector(".email-count");

    try {
        if (showLoadingState) {
            if (countEl) countEl.textContent = "Загрузка...";
            if (listEl) {
                listEl.innerHTML = `<div class="email-placeholder" style="padding: 20px; text-align: center;">Загрузка писем...</div>`;
            }
        }

        const resp = await fetch("/api/queue", {
            method: "GET",
            headers: { "Accept": "application/json" },
            credentials: "same-origin",
        });

        if (resp.status === 401) {
            if (countEl) countEl.textContent = "Не авторизован";
            if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding: 20px; text-align: center;">Нужно войти заново</div>`;
            if (viewEl) viewEl.innerHTML = `<div class="email-placeholder">Нужно войти заново</div>`;
            return false;
        }

        if (!resp.ok) {
            if (countEl) countEl.textContent = "Ошибка";
            if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding: 20px; text-align: center;">Ошибка загрузки писем</div>`;
            if (viewEl) viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
            return false;
        }

        const data = await resp.json();
        const items = data.items || [];
        const grouped = new Map();

        for (const item of items) {
            const uid = item.email_uid ?? item.emailUid ?? item.uid ?? item.id;
            if (!grouped.has(uid)) {
                grouped.set(uid, {
                    uid,
                    id: item.id,
                    sender: item.email_from || item.sender || "Неизвестный отправитель",
                    email: item.email || "",
                    subject: item.email_subject || "(без темы)",
                    date: item.email_date || item.created_at || new Date().toISOString(),
                    status: mapStatus(item.status),
                    content: item.email_body || "",
                    raw_status: item.status || "",
                    document_names: [],
                    predicted_class: item.predicted_class ?? null,
                    model_decision: item.model_decision || "",
                });
            }
            const g = grouped.get(uid);
            if (item.document_name) {
                g.document_names.push(item.document_name);
            }
            if (!g.content && item.email_body) {
                g.content = item.email_body;
            }
        }

        emails = Array.from(grouped.values()).map((g, idx) => ({
            id: g.id ?? (idx + 1),
            uid: g.uid,
            sender: g.sender,
            email: g.email,
            subject: g.subject,
            preview: (g.content || "").replace(/\s+/g, " ").trim().slice(0, 140),
            date: g.date,
            status: g.status,
            content: g.content || "",
            document_names: g.document_names,
            raw_status: g.raw_status,
            predicted_class: g.predicted_class ?? null,
            model_decision: g.model_decision || "",
        }));

        if (countEl) countEl.textContent = `${emails.length} писем`;
        return true;
    } catch (e) {
        console.error("Ошибка при загрузке писем из API:", e);
        if (countEl) countEl.textContent = "Ошибка";
        if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding: 20px; text-align: center;">Ошибка загрузки писем</div>`;
        if (viewEl) viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
        return false;
    }
}

async function refreshEmailsSilently() {
    const previousSelectedId = selectedEmailId;
    const previousEmailsJson = JSON.stringify(emails);
    const loaded = await loadEmailsFromApi(false);
    if (!loaded) return;
    const currentEmailsJson = JSON.stringify(emails);
    if (previousEmailsJson === currentEmailsJson) return;
    renderEmailList();
    if (previousSelectedId) {
        highlightSelectedEmail(previousSelectedId);
        const selectedEmail = emails.find(e => e.id === previousSelectedId);
        if (selectedEmail) {
            applyEmailUpdatesToOpenView(selectedEmail);
        }
    }
}

// ===== ОСНОВНЫЕ ФУНКЦИИ =====
function renderEmailList() {
    const container = document.getElementById('emailsContainer');
    const countEl = document.querySelector('.email-count');
    if (!container) return;
    const sortedEmails = [...emails].sort((a, b) => new Date(b.date) - new Date(a.date));
    if (countEl) countEl.textContent = `${sortedEmails.length} писем`;

    if (sortedEmails.length === 0) {
        container.innerHTML = `<div class="email-placeholder" style="padding: 20px; text-align: center;">📭 Писем пока нет</div>`;
        return;
    }

    container.innerHTML = sortedEmails.map(email => {
        const status = statusConfig[email.status] || statusConfig.waiting;
        return `
            <div class="email-item" data-id="${email.id}">
                <div class="subject">${escapeHtml(email.subject)}</div>
                <div class="email-item-header">
                    <div class="sender">${escapeHtml(email.sender)}</div>
                    <div class="status-badge status-${escapeHtml(email.status)}">${status.name}</div>
                </div>
                <div class="date">${formatDate(email.date)}</div>
            </div>
        `;
    }).join('');

    document.querySelectorAll('.email-item').forEach(item => {
        item.addEventListener('click', () => selectEmail(item.dataset.id));
    });
}

function selectEmail(id) {
    showLoading();
    setTimeout(() => {
        highlightSelectedEmail(id);
        const email = emails.find(e => e.id == parseInt(id, 10));
        if (!email) return;

        const currentStatus = statusConfig[email.status] || statusConfig.waiting;
        const formattedContent = (email.content || "")
            .split('\n')
            .map(line => {
                if (line.trim() === '') return '<br>';
                if (line.includes('•')) return `<p style="margin-left: 20px;">${escapeHtml(line)}</p>`;
                return `<p>${escapeHtml(line)}</p>`;
            })
            .join('');

        const attachmentBlock = email.document_names && email.document_names.length
            ? `<div class="email-attachments"><strong>Вложения:</strong><ul>${email.document_names.map(name => `<li>${escapeHtml(name)}</li>`).join("")}</ul></div>`
            : "";

        const emailMetaSender = email.email ? `${escapeHtml(email.sender)} (${escapeHtml(email.email)})` : `${escapeHtml(email.sender)}`;
        const decisionValue = email.model_decision || "";
        const decisionOptionsHtml = decisionOptions.map(opt => `<option value="${escapeHtml(opt.value)}" ${opt.value === decisionValue ? "selected" : ""}>${escapeHtml(opt.label)}</option>`).join("");

        const decisionBlock = `
            <div class="decision-block">
                <label for="decision-select" class="decision-label">Класс письма:</label>
                <select id="decision-select" class="decision-select">${decisionOptionsHtml}</select>
                <button id="decision-save-btn" class="decision-save-btn">Сохранить</button>
            </div>
        `;

        const emailView = document.getElementById('emailView');
        emailView.innerHTML = `
            <div class="email-card">
                <div class="email-header">
                    <div class="email-header-top">
                        <div class="email-subject">${escapeHtml(email.subject)}</div>
                        <div class="status-block"><div class="status-info"><span class="status-label">Состояние:</span><div class="status-display status-${escapeHtml(email.status)}">${currentStatus.name}</div></div></div>
                    </div>
                    <div class="email-meta"><div><strong>От:</strong> ${emailMetaSender}</div><div><strong>Дата:</strong> ${formatDateTime(email.date)}</div></div>
                </div>
                ${attachmentBlock}
                ${decisionBlock}
                <div class="email-body">${formattedContent || "<p>Текст письма отсутствует</p>"}</div>
            </div>
        `;

        const saveBtn = document.getElementById("decision-save-btn");
        const decisionSelect = document.getElementById("decision-select");
        if (saveBtn && decisionSelect) {
            saveBtn.addEventListener("click", async () => {
                const newDecision = decisionSelect.value;
                try {
                    const resp = await fetch(`/api/queue/${email.id}/decision`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json", "Accept": "application/json" },
                        credentials: "same-origin",
                        body: JSON.stringify({ model_decision: newDecision === "" ? null : newDecision }),
                    });
                    if (!resp.ok) {
                        console.error("Не удалось сохранить решение", resp.status);
                        alert("Не удалось сохранить решение");
                        return;
                    }
                    email.model_decision = newDecision;
                    if (newDecision === "auto_0" || newDecision === "auto_1") {
                        email.status = "clarification";
                    } else if (newDecision === "review") {
                        email.status = "review";
                    }
                    renderEmailList();
                    highlightSelectedEmail(email.id);
                    applyEmailUpdatesToOpenView(email);
                    alert("Решение сохранено");
                } catch (e) {
                    console.error("Ошибка при сохранении решения", e);
                    alert("Ошибка при сохранении решения");
                }
            });
        }
    }, 300);
}

// ===== ФУНКЦИИ ДЛЯ ЧАТА =====
async function loadMaterials() {
    const container = document.getElementById('chat-materials-list');
    if (!container) return [];
    // Показываем загрузку
    container.innerHTML = '<div class="loading-materials">Загрузка материалов...</div>';
    try {
        // TODO: заменить на реальный endpoint, который возвращает список материалов
        // Пока используем заглушку, имитирующую ответ сервера
        let materials = [];
        // Имитация задержки сети
        await new Promise(resolve => setTimeout(resolve, 500));
        // Если у вас есть реальный API, раскомментируйте fetch и закомментируйте заглушку
        /*
        const resp = await fetch('/api/materials', { credentials: 'same-origin' });
        if (resp.ok) {
            const data = await resp.json();
            materials = data.materials || [];
        } else {
            console.warn('Не удалось загрузить материалы, используем заглушку');
            materials = ['Стекло', 'Пластик', 'Ручки'];
        }
        */
        // ЗАГЛУШКА:
        materials = ['Стекло', 'Пластик', 'Ручки'];
        
        if (!materials.length) {
            container.innerHTML = '<div class="materials-empty">Нет доступных материалов</div>';
            return [];
        }
        // Отрисовываем чекбоксы
        container.innerHTML = materials.map(mat => `
            <label><input type="checkbox" value="${escapeHtml(mat)}"> ${escapeHtml(mat)}</label>
        `).join('');
        return materials;
    } catch (err) {
        console.error('Ошибка загрузки материалов:', err);
        container.innerHTML = '<div class="materials-error">Ошибка загрузки материалов</div>';
        return [];
    }
}

async function sendChatData() {
    // Собираем выбранные материалы
    const selectedMaterials = [];
    document.querySelectorAll('#chat-materials-list input[type="checkbox"]:checked').forEach(cb => {
        selectedMaterials.push(cb.value);
    });
    const message = document.getElementById('chat-input').value;
    const isBlacklisted = document.getElementById('blacklist-checkbox').checked;

    const payload = {
        materials: selectedMaterials,
        message: message,
        blacklist: isBlacklisted
    };
    console.log('Отправка в чат:', payload);
    try {
        // TODO: заменить на реальный endpoint для отправки ответа в программу
        // const resp = await fetch('/api/chat/response', {
        //     method: 'POST',
        //     headers: { 'Content-Type': 'application/json' },
        //     credentials: 'same-origin',
        //     body: JSON.stringify(payload)
        // });
        // if (resp.ok) {
        //     alert('Отправлено успешно');
        //     // очистить поля
        //     document.getElementById('chat-input').value = '';
        //     document.getElementById('blacklist-checkbox').checked = false;
        //     document.querySelectorAll('#chat-materials-list input[type="checkbox"]').forEach(cb => cb.checked = false);
        // } else {
        //     alert('Ошибка отправки');
        // }
        // Имитация успеха:
        alert(`Отправлено!\nМатериалы: ${selectedMaterials.join(', ') || 'нет'}\nСообщение: ${message || '(пусто)'}\nЧерный список: ${isBlacklisted ? 'Да' : 'Нет'}`);
        document.getElementById('chat-input').value = '';
        document.getElementById('blacklist-checkbox').checked = false;
        document.querySelectorAll('#chat-materials-list input[type="checkbox"]').forEach(cb => cb.checked = false);
    } catch (err) {
        console.error('Ошибка отправки:', err);
        alert('Ошибка отправки');
    }
}

// ===== ПЕРЕКЛЮЧЕНИЕ ВКЛАДОК И ИНИЦИАЛИЗАЦИЯ ЧАТА =====
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanes = document.querySelectorAll('.tab-pane');

    function switchTab(tabId) {
        tabButtons.forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.tab === tabId) btn.classList.add('active');
        });
        tabPanes.forEach(pane => {
            pane.classList.remove('active');
            if (pane.id === `tab-${tabId}`) pane.classList.add('active');
        });
        // При переключении на вкладку "Чат" загружаем материалы (один раз или каждый раз)
        if (tabId === 'chat') {
            if (!cachedMaterials) {
                loadMaterials().then(mats => { cachedMaterials = mats; });
            } else {
                // если уже загружены, но нужно перерисовать? (может измениться список)
                // можно просто ничего не делать или перерисовать если требуется
                const container = document.getElementById('chat-materials-list');
                if (container && cachedMaterials.length && container.children.length === 0) {
                    container.innerHTML = cachedMaterials.map(mat => `<label><input type="checkbox" value="${escapeHtml(mat)}"> ${escapeHtml(mat)}</label>`).join('');
                }
            }
        }
    }

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            switchTab(btn.dataset.tab);
        });
    });
}

// ===== ИНИЦИАЛИЗАЦИЯ СТРАНИЦЫ =====
document.addEventListener('DOMContentLoaded', async () => {
    const loaded = await loadEmailsFromApi();
    if (!loaded) return;
    renderEmailList();
    if (emails.length > 0) {
        selectEmail(emails[0].id);
    } else {
        const emailView = document.getElementById('emailView');
        if (emailView) emailView.innerHTML = `<div class="email-placeholder">📭 Писем пока нет</div>`;
    }

    // Автообновление каждые 5 секунд
    setInterval(() => {
        refreshEmailsSilently();
    }, 5000);

    // Инициализация вкладок
    initTabs();

    // Обработчик кнопки "Отправить" в чате
    const sendBtn = document.getElementById('chat-send-btn');
    if (sendBtn) {
        sendBtn.addEventListener('click', sendChatData);
    }

    // Предварительная загрузка материалов (опционально, если вкладка "Чат" активна по умолчанию)
    // По умолчанию активна вкладка "Письма", поэтому загрузим материалы только при первом переключении.
});

window.mailClient = { statusConfig };