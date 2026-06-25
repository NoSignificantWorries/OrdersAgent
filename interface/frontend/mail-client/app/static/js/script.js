// ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
let emails = [];
let selectedEmailId = null;
const chatStorage = new Map();

let currentStatusFilter = 'all';
let currentClassFilter = 'all';
let sortNewestFirst = true;
let currentSearchTerm = '';

// ========== КОНФИГУРАЦИЯ ==========
const statusConfig = {
    waiting: { name: "Ожидание" },
    processing: { name: "Обработка" },
    clarification: { name: "Класс определён" },
    review: { name: "Требуется выбор класса" },
    completed: { name: "Выполнена" }
};

const decisionOptions = [
    { value: "", label: "Выберите класс" },
    { value: "auto_0", label: "Заявка" },
    { value: "auto_1", label: "Расчёт" },
    { value: "review", label: "Требуется ручной выбор" }
];

// ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
function formatDate(dateString) {
    const date = new Date(dateString);
    if (isNaN(date)) return "";
    const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    return `${date.getDate()} ${months[date.getMonth()]}`;
}

function formatDateTime(dateString) {
    const date = new Date(dateString);
    if (isNaN(date)) return "";
    return date.toLocaleString("ru-RU");
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? "";
    return div.innerHTML;
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

function showLoading() {
    const emailView = document.getElementById('emailView');
    if (emailView) emailView.innerHTML = `<div class="email-loading-wrapper"><div class="loading"></div></div>`;
}

function highlightSelectedEmail(id) {
    document.querySelectorAll('.email-item').forEach(item => item.classList.remove('selected'));
    const selected = document.querySelector(`.email-item[data-id="${id}"]`);
    if (selected) selected.classList.add('selected');
}

// ========== ЗАГРУЗКА ПИСЕМ ИЗ API ==========
async function loadEmailsFromApi(showLoadingState = true) {
    const listEl = document.getElementById("emailsContainer");
    const viewEl = document.getElementById("emailView");
    const countSpan = document.getElementById("email-count-display");

    try {
        if (showLoadingState) {
            if (countSpan) countSpan.textContent = "Загрузка...";
            if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Загрузка писем...</div>`;
        }
        const resp = await fetch("/api/queue", { method: "GET", headers: { "Accept": "application/json" }, credentials: "same-origin" });
        if (resp.status === 401) {
            if (countSpan) countSpan.textContent = "Не авторизован";
            if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Нужно войти заново</div>`;
            if (viewEl) viewEl.innerHTML = `<div class="email-placeholder">Нужно войти заново</div>`;
            return false;
        }
        if (!resp.ok) {
            if (countSpan) countSpan.textContent = "Ошибка";
            if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
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
            if (item.document_name) g.document_names.push(item.document_name);
            if (!g.content && item.email_body) g.content = item.email_body;
        }

        const newEmails = Array.from(grouped.values()).map((g, idx) => ({
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

        // Восстанавливаем данные чата
        for (const email of newEmails) {
            if (chatStorage.has(email.id)) {
                email.chatItems = chatStorage.get(email.id);
            } else {
                email.chatItems = [
                    { material: "Стекло", answer: "", blacklist: false },
                    { material: "Пластик", answer: "", blacklist: false },
                    { material: "Ручки", answer: "", blacklist: false }
                ];
                chatStorage.set(email.id, email.chatItems);
            }
        }

        emails = newEmails;
        if (countSpan) countSpan.textContent = `${emails.length} писем`;
        return true;
    } catch (e) {
        console.error("Ошибка загрузки писем:", e);
        if (countSpan) countSpan.textContent = "Ошибка";
        if (listEl) listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
        if (viewEl) viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
        return false;
    }
}

// ========== ОТРИСОВКА СПИСКА (с фильтрами, поиском, сортировкой) ==========
function renderEmailList() {
    let filtered = [...emails];

    // Поиск
    if (currentSearchTerm.trim() !== '') {
        const term = currentSearchTerm.toLowerCase();
        filtered = filtered.filter(email =>
            email.subject.toLowerCase().includes(term) ||
            email.sender.toLowerCase().includes(term) ||
            (email.content && email.content.toLowerCase().includes(term))
        );
    }

    // Статус
    if (currentStatusFilter !== 'all') {
        filtered = filtered.filter(e => e.status === currentStatusFilter);
    }

    // Класс
    if (currentClassFilter !== 'all') {
        if (currentClassFilter === '') {
            filtered = filtered.filter(e => !e.model_decision || e.model_decision === '');
        } else {
            filtered = filtered.filter(e => e.model_decision === currentClassFilter);
        }
    }

    // Сортировка
    filtered.sort((a, b) => {
        const dateA = new Date(a.date);
        const dateB = new Date(b.date);
        return sortNewestFirst ? dateB - dateA : dateA - dateB;
    });

    const container = document.getElementById('emailsContainer');
    const countSpan = document.getElementById('email-count-display');
    if (!container) return;

    if (filtered.length === 0) {
        container.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">📭 Писем по заданным критериям не найдено</div>`;
        if (countSpan) countSpan.textContent = `0 писем`;
        return;
    }

    container.innerHTML = filtered.map(email => {
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

    document.querySelectorAll('.email-item').forEach(el => {
        el.addEventListener('click', () => selectEmail(el.dataset.id));
    });

    if (countSpan) countSpan.textContent = `${filtered.length} писем`;
}

// ========== ВЫБОР ПИСЬМА ==========
function selectEmail(id) {
    selectedEmailId = parseInt(id, 10);
    const email = emails.find(e => e.id === selectedEmailId);
    if (!email) return;
    showLoading();
    setTimeout(() => {
        highlightSelectedEmail(id);
        renderEmailCard(email);
        if (document.getElementById('tab-chat').classList.contains('active')) {
            renderChatForEmail(email);
        }
    }, 300);
}

function renderEmailCard(email) {
    const currentStatus = statusConfig[email.status] || statusConfig.waiting;
    const formattedContent = (email.content || "").split('\n').map(line => {
        if (line.trim() === '') return '<br>';
        if (line.includes('•')) return `<p style="margin-left:20px;">${escapeHtml(line)}</p>`;
        return `<p>${escapeHtml(line)}</p>`;
    }).join('');
    const attachmentBlock = email.document_names?.length ? `
        <div class="email-attachments">
            <strong>Вложения:</strong>
            <ul>
                ${email.document_names.map(n => `<li>${escapeHtml(n)}</li>`).join('')}
            </ul>
            <button class="save-all-attachments-btn" data-email-id="${email.id}">Скачать</button>
        </div>
    ` : '';
    const metaSender = email.email ? `${escapeHtml(email.sender)} (${escapeHtml(email.email)})` : escapeHtml(email.sender);
    const decisionValue = email.model_decision || "";
    const decisionHtml = decisionOptions.map(opt => `<option value="${escapeHtml(opt.value)}" ${opt.value === decisionValue ? "selected" : ""}>${escapeHtml(opt.label)}</option>`).join('');

    const emailView = document.getElementById('emailView');
    emailView.innerHTML = `
        <div class="email-card">
            <div class="email-header">
                <div class="email-header-top">
                    <div class="email-subject">${escapeHtml(email.subject)}</div>
                    <div class="status-block"><div class="status-info"><span class="status-label">Состояние:</span><div class="status-display status-${escapeHtml(email.status)}">${currentStatus.name}</div></div></div>
                </div>
                <div class="email-meta"><div><strong>От:</strong> ${metaSender}</div><div><strong>Дата:</strong> ${formatDateTime(email.date)}</div></div>
            </div>
            ${attachmentBlock}
            <div class="decision-block">
                <label for="decision-select" class="decision-label">Класс письма:</label>
                <select id="decision-select" class="decision-select">${decisionHtml}</select>
                <button id="decision-save-btn" class="decision-save-btn">Сохранить</button>
            </div>
            <div class="email-body">${formattedContent || "<p>Текст письма отсутствует</p>"}</div>
        </div>
    `;

    const saveBtn = document.getElementById('decision-save-btn');
    const sel = document.getElementById('decision-select');
    if (saveBtn && sel) {
        saveBtn.onclick = async () => {
            const newVal = sel.value;
            try {
                const resp = await fetch(`/api/queue/${email.id}/decision`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
                    body: JSON.stringify({ model_decision: newVal === "" ? null : newVal })
                });
                if (!resp.ok) throw new Error();
                email.model_decision = newVal;
                if (newVal === "auto_0" || newVal === "auto_1") email.status = "clarification";
                else if (newVal === "review") email.status = "review";
                renderEmailList();
                highlightSelectedEmail(email.id);
                alert("Решение сохранено");
            } catch(e) { alert("Ошибка"); }
        };
    }
    const saveAttachmentsBtn = document.querySelector('.save-all-attachments-btn');
    if (saveAttachmentsBtn) {
        saveAttachmentsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            alert(`Функция сохранения вложений для письма "${email.subject}" будет реализована позже.`);
        });
    }
}

// ========== ЧАТ ==========
function renderChatForEmail(email) {
    const container = document.getElementById('chat-rows-container');
    const submitContainer = document.querySelector('.chat-submit');
    if (!container) return;

    // По умолчанию скрываем кнопку
    if (submitContainer) submitContainer.style.display = 'none';

    if (!email) {
        container.innerHTML = '<div class="chat-placeholder">Выберите письмо</div>';
        return;
    }

    if (!email.chatItems || email.chatItems.length === 0) {
        container.innerHTML = '<div class="chat-placeholder">Нет материалов для этого письма</div>';
        return;
    }

    // Если есть материалы – показываем кнопку
    if (submitContainer) submitContainer.style.display = 'block';

    let html = '';
    email.chatItems.forEach((item, idx) => {
        html += `
            <div class="chat-row" data-row="${idx}">
                <div class="material-name">${escapeHtml(item.material)}</div>
                <input type="text" class="answer-input" style="width: 500px;" value="${escapeHtml(item.answer)}" placeholder="Введите ответ...">
                <label class="blacklist-label">
                    <input type="checkbox" class="blacklist-checkbox" ${item.blacklist ? 'checked' : ''}> Черный список
                </label>
            </div>
        `;
    });
    container.innerHTML = html;

    // Привязываем события
    email.chatItems.forEach((item, idx) => {
        const row = container.querySelector(`.chat-row[data-row="${idx}"]`);
        if (!row) return;
        const input = row.querySelector('.answer-input');
        const chk = row.querySelector('.blacklist-checkbox');
        if (input) {
            input.addEventListener('input', (e) => {
                item.answer = e.target.value;
                chatStorage.set(email.id, email.chatItems);
            });
        }
        if (chk) {
            chk.addEventListener('change', (e) => {
                item.blacklist = e.target.checked;
                chatStorage.set(email.id, email.chatItems);
            });
        }
    });
    // Если статус письма "completed", добавить блок с файлами и кнопкой "Сохранить все"
    if (email.status === 'completed') {
        const resultBlock = document.createElement('div');
        resultBlock.className = 'chat-result-block';
        resultBlock.innerHTML = `
            <div class="email-attachments" style="margin-top: 20px;">
                <strong>Результаты обработки:</strong>
                <ul>
                    <li>Файл результата 1.pdf</li>
                    <li>Файл результата 2.pdf</li>
                </ul>
                <button class="save-all-results-btn" data-email-id="${email.id}">Скачать</button>
            </div>
        `;
        container.appendChild(resultBlock);
        
        const saveResultsBtn = resultBlock.querySelector('.save-all-results-btn');
        if (saveResultsBtn) {
            saveResultsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                alert(`Функция сохранения файлов результатов для письма "${email.subject}" будет реализована позже.`);
            });
        }
    }
}

async function sendChatData() {
    const email = emails.find(e => e.id === selectedEmailId);
    if (!email) { alert("Выберите письмо"); return; }
    if (!email.chatItems || email.chatItems.length === 0) {
        alert("Нет материалов для этого письма");
        return;
    }
    const data = email.chatItems.map(item => ({
        material: item.material,
        answer: item.answer,
        blacklist: item.blacklist
    }));
    console.log("Отправка для письма", email.id, data);
    alert(`Отправлено для письма "${email.subject}"\n${JSON.stringify(data, null, 2)}`);
    // замените на реальный POST-запрос
}

// ========== ВКЛАДКИ ==========
function initTabs() {
    const btns = document.querySelectorAll('.tab-button');
    const panes = document.querySelectorAll('.tab-pane');
    function switchTab(tabId) {
        btns.forEach(btn => { btn.classList.remove('active'); if (btn.dataset.tab === tabId) btn.classList.add('active'); });
        panes.forEach(pane => { pane.classList.remove('active'); if (pane.id === `tab-${tabId}`) pane.classList.add('active'); });
        if (tabId === 'chat') {
            const email = emails.find(e => e.id === selectedEmailId);
            renderChatForEmail(email);
        } else if (tabId === 'emails') {
            if (selectedEmailId) renderEmailCard(emails.find(e => e.id === selectedEmailId));
        }
    }
    btns.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
}

// ========== АВТООБНОВЛЕНИЕ ==========
async function refreshEmailsSilently() {
    const prevId = selectedEmailId;
    await loadEmailsFromApi(false);
    renderEmailList();
    if (prevId && emails.find(e => e.id === prevId)) {
        highlightSelectedEmail(prevId);
        if (document.getElementById('tab-chat').classList.contains('active')) {
            renderChatForEmail(emails.find(e => e.id === prevId));
        } else {
            renderEmailCard(emails.find(e => e.id === prevId));
        }
    } else {
        // если выбранного письма больше нет, сбрасываем чат и скрываем кнопку
        if (document.getElementById('tab-chat').classList.contains('active')) {
            renderChatForEmail(null);
        }
    }
    // дополнительная страховка: если писем нет, скрыть кнопку
    if (emails.length === 0) {
        const submitContainer = document.querySelector('.chat-submit');
        if (submitContainer) submitContainer.style.display = 'none';
    }
}

// ========== ИНИЦИАЛИЗАЦИЯ ==========
document.addEventListener('DOMContentLoaded', async () => {
    await loadEmailsFromApi();
    renderEmailList();
    if (emails.length > 0) selectEmail(emails[0].id);
    setInterval(refreshEmailsSilently, 5000);
    initTabs();
    document.getElementById('chat-send-btn').addEventListener('click', sendChatData);

    // === ПОИСК ===
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            currentSearchTerm = e.target.value;
            renderEmailList();
        });
    }

    // === ФИЛЬТР-ПАНЕЛЬ ===
    const filterToggle = document.getElementById('filter-toggle-btn');
    const filterPanel = document.getElementById('filter-panel');
    const applyBtn = document.getElementById('apply-filters-btn');
    const closeFilter = document.getElementById('close-filter-panel');
    const statusSelect = document.getElementById('status-filter-select');
    const classSelect = document.getElementById('class-filter-select');
    const sortNewestBtn = document.getElementById('sort-newest-btn');
    const sortOldestBtn = document.getElementById('sort-oldest-btn');

    function openFilterPanel() {
        filterPanel.style.display = 'block';
        statusSelect.value = currentStatusFilter;
        classSelect.value = currentClassFilter;
        if (sortNewestFirst) {
            sortNewestBtn.classList.add('active');
            sortOldestBtn.classList.remove('active');
        } else {
            sortOldestBtn.classList.add('active');
            sortNewestBtn.classList.remove('active');
        }
    }
    function closeFilterPanel() {
        filterPanel.style.display = 'none';
    }
    function applyFilters() {
        currentStatusFilter = statusSelect.value;
        currentClassFilter = classSelect.value;
        sortNewestFirst = sortNewestBtn.classList.contains('active');
        renderEmailList();
        closeFilterPanel();
    }

    if (filterToggle) filterToggle.addEventListener('click', openFilterPanel);
    if (applyBtn) applyBtn.addEventListener('click', applyFilters);
    if (closeFilter) closeFilter.addEventListener('click', closeFilterPanel);

    // закрытие при клике вне панели
    document.addEventListener('click', (e) => {
        if (filterPanel && filterPanel.style.display === 'block') {
            if (!filterPanel.contains(e.target) && e.target !== filterToggle && !filterToggle.contains(e.target)) {
                closeFilterPanel();
            }
        }
    });

    if (sortNewestBtn && sortOldestBtn) {
        sortNewestBtn.addEventListener('click', () => {
            sortNewestBtn.classList.add('active');
            sortOldestBtn.classList.remove('active');
        });
        sortOldestBtn.addEventListener('click', () => {
            sortOldestBtn.classList.add('active');
            sortNewestBtn.classList.remove('active');
        });
    }
});