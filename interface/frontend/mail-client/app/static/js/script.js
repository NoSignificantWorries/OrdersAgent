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
    waiting:    { name: "Ожидание" },
    processing: { name: "Обработка" },
    review:     { name: "Требуется ручная проверка" },
    completed:  { name: "Завершено" },
    error:      { name: "Ошибка" }
};

const decisionOptions = [
    { value: "",        label: "Выберите класс" },
    { value: "auto_0",  label: "Заявка" },
    { value: "auto_1",  label: "Расчёт" }
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

function mapTaskStatusToUiStatus(taskStatus) {
    switch ((taskStatus || "").toLowerCase()) {
        case "new":
            return "waiting";          // только что создана
        case "ml_processing":
            return "processing";       // LLM сейчас считает
        case "ml_classified":
            return "completed";        // уверенное авто-решение
        case "ml_low_confidence":
            return "review";           // требуется ручная проверка
        case "excel_ambiguous":
            return "review";           // спорный Excel, тоже на ручной разбор
        case "manual_review_done":
            return "completed";        // ручная проверка сделана
        case "completed":
            return "completed";        // финальный статус (если будешь использовать)
        case "error":
            return "error";
        default:
            return "waiting";
    }
}

function getStatusName(uiStatus) {
    return (statusConfig[uiStatus] || { name: "Неизвестно" }).name;
}

function canManualDecision(emailItem) {
    const status = (emailItem?.task_status || "").toLowerCase();
    const decision = (emailItem?.model_decision || "").toLowerCase();

    // Разрешаем ручную установку класса,
    // если модель сказала "review" или статус = ml_low_confidence
    return status === 'ml_low_confidence' || decision === 'review';
}

function showLoading() {
    const emailView = document.getElementById('emailView');
    if (emailView) {
        emailView.innerHTML = `<div class="email-loading-wrapper"><div class="loading"></div></div>`;
    }
}

function highlightSelectedEmail(id) {
    document.querySelectorAll('.email-item').forEach(item => item.classList.remove('selected'));
    const selected = document.querySelector(`.email-item[data-id="${id}"]`);
    if (selected) selected.classList.add('selected');
}


// ========== НОРМАЛИЗАЦИЯ ДАННЫХ API ==========
function normalizeApiItem(item, idx) {
    const output = (item.outputdata && typeof item.outputdata === "object") ? item.outputdata : {};
    const documents = Array.isArray(item.documents) ? item.documents : [];

    const taskStatus = item.status || "";
    const uiStatus = mapTaskStatusToUiStatus(taskStatus);

    const emailContent = item.rawemail || item.emailbody || "";
    const normalized = {
        id: item.id ?? idx + 1,
        email_id: item.emailid ?? null,
        mailbox: item.mailbox || "",
        uid: item.emailuid ?? null,
        sender: item.emailfrom || "Неизвестный отправитель",
        subject: item.emailsubject || "(без темы)",
        date: item.emaildate || item.createdat || new Date().toISOString(),
        content: emailContent,
        preview: emailContent.replace(/\s+/g, " ").trim().slice(0, 140),

        prob_1: output.prob_1 ?? item.prob1 ?? null,
        predicted_class: output.predicted_class ?? item.predictedclass ?? null,
        model_decision: output.model_decision ?? item.modeldecision ?? "",

        task: {
            id: item.id ?? null,
            type: item.type || null,
            status: item.status || null,
            priority: item.priority ?? 100,
            input_data: item.inputdata || {},
            output_data: output,
            assigned_to: item.assignedto ?? null,
            error_message: item.errormessage || "",
            attempts: item.attempts ?? 0,
            max_attempts: item.maxattempts ?? 3,
            created_at: item.taskcreatedat || null,
            started_at: item.taskstartedat || null,
            completed_at: item.taskcompletedat || null
        },

        task_status: taskStatus,
        status: uiStatus,

        documents,
        document_names: documents
            .map(doc => doc?.document_name)
            .filter(name => name && String(name).trim() !== ""),
    };

    if (chatStorage.has(normalized.id)) {
        normalized.chatItems = chatStorage.get(normalized.id);
    } else {
        normalized.chatItems = [
            { material: "Стекло",  answer: "", blacklist: false },
            { material: "Пластик", answer: "", blacklist: false },
            { material: "Ручки",   answer: "", blacklist: false }
        ];
        chatStorage.set(normalized.id, normalized.chatItems);
    }

    return normalized;
}


// ========== ЗАГРУЗКА ПИСЕМ ИЗ API ==========
async function loadEmailsFromApi(showLoadingState = true) {
    const listEl = document.getElementById("emailsContainer");
    const viewEl = document.getElementById("emailView");
    const countSpan = document.getElementById("email-count-display");

    try {
        if (showLoadingState) {
            if (countSpan) countSpan.textContent = "Загрузка...";
            if (listEl) {
                listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Загрузка писем...</div>`;
            }
        }

        const resp = await fetch("/api/queue", {
            method: "GET",
            headers: { "Accept": "application/json" },
            credentials: "same-origin"
        });

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
        const items = Array.isArray(data.items) ? data.items : [];

        emails = items.map((item, idx) => normalizeApiItem(item, idx));

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


// ========== ОТРИСОВКА СПИСКА ==========
function renderEmailList() {
    let filtered = [...emails];

    if (currentSearchTerm.trim() !== '') {
        const term = currentSearchTerm.toLowerCase();
        filtered = filtered.filter(email =>
            email.subject.toLowerCase().includes(term) ||
            email.sender.toLowerCase().includes(term) ||
            email.mailbox.toLowerCase().includes(term) ||
            (email.content && email.content.toLowerCase().includes(term))
        );
    }

    if (currentStatusFilter !== 'all') {
        filtered = filtered.filter(e => e.status === currentStatusFilter);
    }

    if (currentClassFilter !== 'all') {
        if (currentClassFilter === '') {
            filtered = filtered.filter(e => !e.model_decision || e.model_decision === '');
        } else {
            filtered = filtered.filter(e => e.model_decision === currentClassFilter);
        }
    }

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

    container.innerHTML = filtered.map(email => `
        <div class="email-item" data-id="${email.id}">
            <div class="subject">${escapeHtml(email.subject)}</div>
            <div class="email-item-header">
                <div class="sender">${escapeHtml(email.sender)}</div>
                <div class="status-badge status-${escapeHtml(email.status)}">${escapeHtml(getStatusName(email.status))}</div>
            </div>
            <div class="date">${formatDate(email.date)}</div>
        </div>
    `).join('');

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
        const chatTab = document.getElementById('tab-chat');
        if (chatTab && chatTab.classList.contains('active')) {
            renderChatForEmail(email);
        }
    }, 300);
}


// ========== КАРТОЧКА ПИСЬМА ==========
function renderEmailCard(email) {
    const formattedContent = (email.content || "").split('\n').map(line => {
        if (line.trim() === '') return '<br>';
        if (line.includes('•')) return `<p style="margin-left:20px;">${escapeHtml(line)}</p>`;
        return `<p>${escapeHtml(line)}</p>`;
    }).join('') || '<p>...</p>';

    const docsWithName = (email.documents || []).filter(
        doc => doc && doc.document_name && String(doc.document_name).trim() !== ""
    );

    const attachmentBlock = docsWithName.length ? `
        <div class="email-attachments">
            <strong>Вложения:</strong>
            <ul>
                ${docsWithName.map(doc => `
                    <li>${escapeHtml(doc.document_name)}</li>
                `).join('')}
            </ul>
            <button class="save-all-attachments-btn" data-email-id="${email.id}">Скачать</button>
        </div>
    ` : '';

    const decisionValue = email.model_decision || "";
    const decisionHtml = decisionOptions.map(opt => `
        <option value="${escapeHtml(opt.value)}" ${opt.value === decisionValue ? "selected" : ""}>
            ${escapeHtml(opt.label)}
        </option>
    `).join('');

    const manualAllowed = canManualDecision(email);
    const taskStatusName = getStatusName(email.status);

    const decisionBlock = manualAllowed && email.task ? `
        <div class="decision-block">
            <label for="decision-select" class="decision-label">Класс письма</label>
            <select id="decision-select" class="decision-select">
                ${decisionHtml}
            </select>
            <button id="decision-save-btn" class="decision-save-btn">Сохранить</button>
        </div>
    ` : '';

    const emailView = document.getElementById('emailView');
    if (!emailView) return;

    emailView.innerHTML = `
        <div class="email-card">
            <div class="email-header">
                <div class="email-header-top">
                    <div class="email-subject">${escapeHtml(email.subject)}</div>
                    <div class="status-block">
                        <div class="status-info">
                            <span class="status-label">Состояние:</span>
                            <div class="status-display status-${escapeHtml(email.status)}">${escapeHtml(taskStatusName)}</div>
                        </div>
                    </div>
                </div>

                <div class="email-meta">
                    <div><strong>От:</strong> ${escapeHtml(email.sender)}</div>
                    <div><strong>UID:</strong> ${escapeHtml(String(email.uid ?? ""))}</div>
                    <div><strong>Дата:</strong> ${formatDateTime(email.date)}</div>
                </div>
            </div>

            ${attachmentBlock}
            ${decisionBlock}

            <div class="email-body">
                ${formattedContent}
            </div>
        </div>
    `;

    const saveBtn = document.getElementById('decision-save-btn');
    const sel = document.getElementById('decision-select');

    if (saveBtn && sel && manualAllowed && email.task?.id) {
        saveBtn.onclick = async () => {
            const newVal = sel.value || null;

            if (newVal !== "auto_0" && newVal !== "auto_1") {
                alert("Выберите итоговый класс: «Заявка» или «Расчёт».");
                return;
            }

            try {
                const resp = await fetch(`/api/queue/${email.task.id}/decision`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        model_decision: newVal
                    })
                });

                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    throw new Error(data.detail || "Ошибка сохранения");
                }

                const task = data.task || {};
                const output = task.output_data || {};

                email.model_decision = output.model_decision || email.model_decision || newVal || "";
                email.predicted_class = output.predicted_class ?? email.predicted_class;
                email.prob_1 = output.prob_1 ?? email.prob_1;

                if (email.task) {
                    email.task.status = task.status || email.task.status;
                    email.task.assigned_to = task.assigned_to ?? email.task.assigned_to;
                    email.task.output_data = output;
                    email.task.completed_at = task.completed_at || email.task.completed_at;

                    email.task_status = email.task.status;
                    email.status = mapTaskStatusToUiStatus(email.task.status);
                }

                renderEmailList();
                highlightSelectedEmail(email.id);
                renderEmailCard(email);

                alert("Решение сохранено");
            } catch (e) {
                console.error(e);
                alert(e.message || "Ошибка");
            }
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

    if (submitContainer) submitContainer.style.display = 'none';

    if (!email) {
        container.innerHTML = '<div class="chat-placeholder">Выберите письмо</div>';
        return;
    }

    if (!email.chatItems || email.chatItems.length === 0) {
        container.innerHTML = '<div class="chat-placeholder">Нет материалов для этого письма</div>';
        return;
    }

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
    if (!email) {
        alert("Выберите письмо");
        return;
    }

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
}


// ========== ВКЛАДКИ ==========
function initTabs() {
    const btns = document.querySelectorAll('.tab-button');
    const panes = document.querySelectorAll('.tab-pane');

    function switchTab(tabId) {
        btns.forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.tab === tabId) btn.classList.add('active');
        });

        panes.forEach(pane => {
            pane.classList.remove('active');
            if (pane.id === `tab-${tabId}`) pane.classList.add('active');
        });

        if (tabId === 'chat') {
            const email = emails.find(e => e.id === selectedEmailId);
            renderChatForEmail(email);
        } else if (tabId === 'emails') {
            if (selectedEmailId) {
                renderEmailCard(emails.find(e => e.id === selectedEmailId));
            }
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
        const currentEmail = emails.find(e => e.id === prevId);
        highlightSelectedEmail(prevId);

        const chatTab = document.getElementById('tab-chat');
        if (chatTab && chatTab.classList.contains('active')) {
            renderChatForEmail(currentEmail);
        } else {
            renderEmailCard(currentEmail);
        }
    } else {
        const chatTab = document.getElementById('tab-chat');
        if (chatTab && chatTab.classList.contains('active')) {
            renderChatForEmail(null);
        }
    }

    if (emails.length === 0) {
        const submitContainer = document.querySelector('.chat-submit');
        if (submitContainer) submitContainer.style.display = 'none';
    }
}


// ========== ИНИЦИАЛИЗАЦИЯ ==========
document.addEventListener('DOMContentLoaded', async () => {
    await loadEmailsFromApi();
    renderEmailList();

    if (emails.length > 0) {
        selectEmail(emails[0].id);
    }

    setInterval(refreshEmailsSilently, 5000);
    initTabs();

    const chatSendBtn = document.getElementById('chat-send-btn');
    if (chatSendBtn) {
        chatSendBtn.addEventListener('click', sendChatData);
    }

    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            currentSearchTerm = e.target.value;
            renderEmailList();
        });
    }

    const filterToggle = document.getElementById('filter-toggle-btn');
    const filterPanel = document.getElementById('filter-panel');
    const applyBtn = document.getElementById('apply-filters-btn');
    const closeFilter = document.getElementById('close-filter-panel');
    const statusSelect = document.getElementById('status-filter-select');
    const classSelect = document.getElementById('class-filter-select');
    const sortNewestBtn = document.getElementById('sort-newest-btn');
    const sortOldestBtn = document.getElementById('sort-oldest-btn');

    function openFilterPanel() {
        if (!filterPanel) return;
        filterPanel.style.display = 'block';
        if (statusSelect) statusSelect.value = currentStatusFilter;
        if (classSelect) classSelect.value = currentClassFilter;

        if (sortNewestBtn && sortOldestBtn) {
            if (sortNewestFirst) {
                sortNewestBtn.classList.add('active');
                sortOldestBtn.classList.remove('active');
            } else {
                sortOldestBtn.classList.add('active');
                sortNewestBtn.classList.remove('active');
            }
        }
    }

    function closeFilterPanel() {
        if (filterPanel) filterPanel.style.display = 'none';
    }

    function applyFilters() {
        if (statusSelect) currentStatusFilter = statusSelect.value;
        if (classSelect) currentClassFilter = classSelect.value;
        if (sortNewestBtn) sortNewestFirst = sortNewestBtn.classList.contains('active');
        renderEmailList();
        closeFilterPanel();
    }

    if (filterToggle) filterToggle.addEventListener('click', openFilterPanel);
    if (applyBtn) applyBtn.addEventListener('click', applyFilters);
    if (closeFilter) closeFilter.addEventListener('click', closeFilterPanel);

    document.addEventListener('click', (e) => {
        if (filterPanel && filterPanel.style.display === 'block' && filterToggle) {
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