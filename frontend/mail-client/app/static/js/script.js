// ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
let emails = [];
let selectedEmailId = null;
const chatStorage = new Map();

let currentStatusFilter = 'all';
let currentClassFilter = 'all';
let sortNewestFirst = true;
let currentSearchTerm = '';

let isMaterialInputComposing = false;
let pendingSilentRefresh = false;
let refreshSeq = 0;

// ========== КОНФИГУРАЦИЯ ==========
const statusConfig = {
    waiting:    { name: "Ожидание" },
    processing: { name: "Обработка" },
    ml_review:     { name: "Выберите класс" },
    materials_review: { name: "Требуются материалы" },
    question: {name: "Вопрос"},
    completed:  { name: "Завершено" },
    error:      { name: "Ошибка" }
};

const decisionOptions = [
    { value: "",        label: "Выберите класс" },
    { value: "request",  label: "Заявка" },
    { value: "calculation",  label: "Расчёт" },
    { value: "question", label: "Вопрос" }
];


// ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
function isEditingMaterialInput() {
    const active = document.activeElement;
    return !!(
        active &&
        active.classList &&
        active.classList.contains('answer-input')
    );
}

function isChatTabActive() {
    const chatTab = document.getElementById('tab-chat');
    return !!(chatTab && chatTab.classList.contains('active'));
}

function isMaterialInputProtected() {
    return isChatTabActive() && (isEditingMaterialInput() || isMaterialInputComposing);
}

function bindMaterialInputEvents(input, item, email) {
    if (!input) return;

    input.addEventListener('compositionstart', () => {
        isMaterialInputComposing = true;
    });

    input.addEventListener('compositionend', (e) => {
        isMaterialInputComposing = false;
        item.answer = e.target.value;
        chatStorage.set(email.id, email.chatItems);

        if (pendingSilentRefresh && !isEditingMaterialInput()) {
            pendingSilentRefresh = false;
            refreshEmailsSilently();
        }
    });

    input.addEventListener('blur', (e) => {
        isMaterialInputComposing = false;
        item.answer = e.target.value;
        chatStorage.set(email.id, email.chatItems);

        setTimeout(() => {
            if (!isEditingMaterialInput() && pendingSilentRefresh) {
                pendingSilentRefresh = false;
                refreshEmailsSilently();
            }
        }, 0);
    });

    input.addEventListener('input', (e) => {
        item.answer = e.target.value;
        chatStorage.set(email.id, email.chatItems);

        if (e.isComposing) {
            isMaterialInputComposing = true;
        }
    });
}

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

async function downloadBlob(url, filename) {
    const resp = await fetch(url, {
        method: 'GET',
        credentials: 'same-origin'
    });

    if (!resp.ok) {
        let message = 'Ошибка скачивания файла';

        try {
            const data = await resp.json();
            if (data && data.detail) {
                message = data.detail;
            }
        } catch (_) {}

        throw new Error(message);
    }

    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename || 'file';
    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function downloadEmailAttachments(email) {
    const docs = getDisplayDocuments(email).filter(doc => doc && doc.id);

    if (!docs.length) {
        alert("Нет файлов для скачивания");
        return;
    }

    try {
        for (const doc of docs) {
            await downloadBlob(
                `/api/documents/${doc.id}/download`,
                doc.document_name
            );
        }
    } catch (e) {
        console.error(e);
        alert(e.message || "Ошибка скачивания файлов");
    }
}

async function loadAvailableResultDocuments(taskId) {
    const resp = await fetch(`/api/tasks/${taskId}/result-documents`, {
        method: 'GET',
        credentials: 'same-origin'
    });

    if (!resp.ok) {
        let message = 'Не удалось получить список результирующих файлов';

        try {
            const data = await resp.json();
            if (data && data.detail) {
                message = data.detail;
            }
        } catch (_) {}

        throw new Error(message);
    }

    const data = await resp.json();
    return data.documents || [];
}

async function downloadAvailableResultDocuments(docs) {
    if (!docs.length) {
        alert("Нет готовых файлов для скачивания");
        return;
    }

    for (const doc of docs) {
        await downloadBlob(
            `/api/documents/${doc.id}/result-download`,
            doc.filename || `result-${doc.id}`
        );
    }
}

function mapTaskStatusToUiStatus(taskStatus) {
    switch ((taskStatus || "").toLowerCase()) {
        case "new":
            return "waiting";

        case "downloaded":
            return "waiting";

        case "files_saved":
            return "waiting";

        case "ml_review":
            return "ml_review";

        case "materials_review":
            return "materials_review";

        case "ml_classified":
            return "processing";

        case "manual_review_done":
            return "processing";

        case "question":
            return "question";

        case "completed":
            return "completed";

        case "error":
            return "error";

        default:
            return "processing";
    }
}

function getStatusName(uiStatus) {
    return (statusConfig[uiStatus] || { name: "Неизвестно" }).name;
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

function extractMaterialNames(value) {
    if (!value) return [];

    if (Array.isArray(value)) {
        return value.flatMap(item => {
            if (typeof item === "string") {
                const s = item.trim();
                return s ? [s] : [];
            }

            if (item && typeof item === "object" && !Array.isArray(item)) {
                return Object.keys(item)
                    .map(k => String(k).trim())
                    .filter(Boolean);
            }

            return [];
        });
    }

    if (value && typeof value === "object") {
        return Object.keys(value)
            .map(k => String(k).trim())
            .filter(Boolean);
    }

    return [];
}

function extractMaterialsFromOutput(output) {
    if (!output || typeof output !== "object") return [];

    // Если output_data сам является массивом материалов
    if (Array.isArray(output)) {
        return extractMaterialNames(output);
    }

    const candidates = [
        output.queries,
        output.requests,
        output.materials,
        output.material_queries,
        output.output_data,
        output.data,
        output.items,
        output.result
    ];

    for (const value of candidates) {
        const names = extractMaterialNames(value);
        if (names.length > 0) return names;
    }

    // если во всем output_data есть хоть одно поле-массив/объект с материалами
    for (const value of Object.values(output)) {
        const names = extractMaterialNames(value);
        if (names.length > 0) return names;
    }

    return [];
}

function getDisplayDocuments(email) {
    const docs = Array.isArray(email?.documents) ? email.documents : [];
    const seenNames = new Set();

    return docs.filter(doc => {
        const documentName = String(doc?.document_name ?? "").trim();
        if (!documentName) return false;

        const key = documentName.toLowerCase();

        if (seenNames.has(key)) return false;
        seenNames.add(key);
        return true;
    });
}

function buildChatItemsFromOutput(output, emailId) {
    const materials = extractMaterialsFromOutput(output);

    const manualDecision =
        output &&
        !Array.isArray(output) &&
        output.manual_decision &&
        typeof output.manual_decision === "object" &&
        !Array.isArray(output.manual_decision)
            ? output.manual_decision
            : {};

    const chatItems = materials.map((material) => {
        const saved = manualDecision[material];
        return {
            material,
            answer: Array.isArray(saved) ? String(saved[0] ?? "") : "",
            blacklist: Array.isArray(saved) ? Boolean(saved[1]) : false
        };
    });

    const cached = chatStorage.get(emailId);
    if (Array.isArray(cached) && cached.length > 0) {
        return chatItems.map(item => {
            const fromCache = cached.find(x => x.material === item.material);
            return fromCache
                ? { ...item, answer: fromCache.answer, blacklist: fromCache.blacklist }
                : item;
        });
    }

    return chatItems;
}

function canCloseTask(email) {
  const status = String(
    email?.task_status || email?.task?.status || email?.status || ''
  ).toLowerCase();

  return ['question', 'error', 'completed'].includes(status);
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
            document_id: item.documentid ?? null,
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

    normalized.chatItems = buildChatItemsFromOutput(output, normalized.id);
    chatStorage.set(normalized.id, normalized.chatItems);

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
        filtered = filtered.filter(e => {
            if (currentStatusFilter === 'manual_review') {
                return e.status === 'materials_review' || e.status === 'ml_review';
            }

            return e.status === currentStatusFilter;
        });
    }

    if (currentClassFilter !== 'all') {
        filtered = filtered.filter(e => {
            const decision = String(e.model_decision ?? '').trim().toLowerCase();
            const isUndefinedClass = decision === '' || decision === 'review';

            if (currentClassFilter === 'undefined_only') {
                return isUndefinedClass;
            }

            return decision === currentClassFilter || isUndefinedClass;
        });
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

    const docsWithName = getDisplayDocuments(email);

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

    const taskStatusName = getStatusName(email.status);

    const decisionBlock = email.task ? `
        <div class="decision-block">
            <label for="decision-select" class="decision-label">Класс письма</label>
            <select id="decision-select" class="decision-select">
                ${decisionHtml}
            </select>
            <button id="decision-save-btn" class="decision-save-btn">Сохранить</button>
        </div>
    ` : '';

    const closeTaskBlock = canCloseTask(email) && email.task?.id ? `
        <div class="danger-zone">
        <button id="close-task-btn" class="close-task-btn">
            Завершить задачу
        </button>
        </div>
    ` : '';

    let errorIconHtml = '';
    if (email.status === 'error') {
        let errorText = email.task?.error_message || "Ошибка неизвестна";
        
        errorIconHtml = `
            <div class="error-tooltip-container">
                <div class="error-question-mark" data-tooltip="${escapeHtml(errorText)}">?</div>
            </div>
        `;
    }

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
                            ${errorIconHtml}
                        </div>
                    </div>
                </div>

                <div class="email-meta">
                    <div><strong>От:</strong> ${escapeHtml(email.sender)}</div>
                    <div><strong>Дата:</strong> ${formatDateTime(email.date)}</div>
                </div>
            </div>

            ${attachmentBlock}
            ${decisionBlock}
            ${closeTaskBlock}

            <div class="email-body">
                ${formattedContent}
            </div>
        </div>
    `;

    const closeTaskBtn = document.getElementById('close-task-btn');
    if (closeTaskBtn) {
    closeTaskBtn.addEventListener('click', async () => {
        const confirmed = window.confirm(
        'Письмо и связанные файлы будут удалены без возможности восстановления. Продолжить?'
        );

        if (!confirmed) return;

        closeTaskBtn.disabled = true;

        try {
        const realEmailId = email.email_id || email.id;

        const resp = await fetch(`/api/emails/${realEmailId}`, {
            method: 'DELETE',
            credentials: 'same-origin',
        });

        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.detail || 'Не удалось удалить письмо');
        }

        emails = emails.filter(item => (item.email_id || item.id) !== realEmailId);
        chatStorage.delete(email.id);
        selectedEmailId = null;

        renderEmailList();

        if (emails.length > 0) {
            selectEmail(emails[0].id);
        } else {
            const emailView = document.getElementById('emailView');
            if (emailView) {
                emailView.innerHTML = '<div class="email-placeholder">Письма отсутствуют</div>';
            }
        }

        alert('Задача завершена, письмо и файлы удалены');
    } catch (e) {
        console.error(e);
        alert(e.message || 'Ошибка удаления');
        closeTaskBtn.disabled = false;
    }
    });
    }

    const saveBtn = document.getElementById('decision-save-btn');
    const sel = document.getElementById('decision-select');

    if (saveBtn && sel && email.task?.id) {
        saveBtn.onclick = async () => {
            const newVal = sel.value || null;

            if (newVal !== "request" && newVal !== "calculation" && newVal !== "question") {
                alert("Выберите итоговый класс: «Заявка», «Расчёт» или «Вопрос».");
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
        saveAttachmentsBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await downloadEmailAttachments(email);
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

    const taskStatus = (email.task_status || '').toLowerCase();

    if (taskStatus === 'completed') {
        if (!email?.task?.id) {
            container.innerHTML = '<div class="chat-placeholder">У письма нет связанной задачи</div>';
            return;
        }

        container.innerHTML = '<div class="chat-placeholder">Загрузка готовых файлов...</div>';

        loadAvailableResultDocuments(email.task.id)
            .then((docs) => {
                if (!docs.length) {
                    container.innerHTML = '<div class="chat-placeholder">Готовые файлы не найдены</div>';
                    return;
                }

                const filesHtml = docs.map(doc => {
                    const filename = doc?.filename || `document-${doc.id}`;
                    return `<li>${escapeHtml(String(filename))}</li>`;
                }).join('');

                container.innerHTML = `
                    <div class="email-attachments">
                        <strong>Готовые файлы:</strong>
                        <ul>
                            ${filesHtml}
                        </ul>
                        <button class="save-all-attachments-btn" data-email-id="${email.id}">
                            Скачать
                        </button>
                    </div>
                `;

                const downloadBtn = container.querySelector('.save-all-attachments-btn');
                if (downloadBtn) {
                    downloadBtn.addEventListener('click', async (e) => {
                        e.stopPropagation();

                        try {
                            await downloadAvailableResultDocuments(docs);
                        } catch (err) {
                            console.error(err);
                            alert(err.message || 'Ошибка скачивания результирующих файлов');
                        }
                    });
                }
            })
            .catch((err) => {
                console.error(err);
                container.innerHTML = `<div class="chat-placeholder">${escapeHtml(err.message || 'Ошибка загрузки файлов')}</div>`;
            });

        return;
    }

    if (taskStatus !== 'materials_review') {
        container.innerHTML = '<div class="chat-placeholder">Для этого письма ручной выбор материалов не требуется</div>';
        return;
    }

    if (!email.chatItems || email.chatItems.length === 0) {
        container.innerHTML = '<div class="chat-placeholder">В output_data нет материалов для ручного выбора</div>';
        return;
    }

    if (submitContainer) submitContainer.style.display = 'block';

    let html = '';
    email.chatItems.forEach((item, idx) => {
        html += `
            <div class="chat-row" data-row="${idx}">
                <div class="chat-row-top">
                    <div class="material-name">${escapeHtml(item.material)}</div>
                    <label class="blacklist-label">
                        <input type="checkbox" class="blacklist-checkbox" ${item.blacklist ? 'checked' : ''}>
                        Черный список
                    </label>
                </div>

                <div class="chat-row-bottom">
                    <input
                        type="text"
                        class="answer-input"
                        value="${escapeHtml(item.answer)}"
                        placeholder="Введите ответ..."
                    >
                </div>
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
            bindMaterialInputEvents(input, item, email);
        }

        if (chk) {
            chk.addEventListener('change', (e) => {
                item.blacklist = e.target.checked;
                chatStorage.set(email.id, email.chatItems);
            });
        }
    });
}

async function sendChatData() {
    const email = emails.find(e => e.id === selectedEmailId);
    if (!email) {
        alert("Выберите письмо");
        return;
    }

    if (!email.task?.id) {
        alert("У письма нет связанной задачи");
        return;
    }

    if ((email.task_status || '').toLowerCase() !== 'materials_review') {
        alert("Ручной ввод доступен только для задач со статусом materials_review");
        return;
    }

    if (!email.chatItems || email.chatItems.length === 0) {
        alert("Нет материалов для этого письма");
        return;
    }

    const hasEmpty = email.chatItems.some(item => !String(item.answer || '').trim());
    if (hasEmpty) {
        alert("Заполните все поля перед сохранением");
        return;
    }

    const manualDecision = {};
    email.chatItems.forEach(item => {
        manualDecision[item.material] = [
            String(item.answer || "").trim(),
            Boolean(item.blacklist)
        ];
    });

    try {
        const resp = await fetch(`/api/queue/${email.task.id}/manual-decision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                manual_decision: manualDecision
            })
        });

        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.detail || "Ошибка сохранения");
        }

        const savedEmailId = email.id;

        chatStorage.delete(email.id);

        await loadEmailsFromApi(false);
        renderEmailList();

        const freshEmail = emails.find(e => e.id === savedEmailId);

        if (freshEmail) {
            selectedEmailId = freshEmail.id;
            highlightSelectedEmail(freshEmail.id);

            const chatTab = document.getElementById('tab-chat');
            if (chatTab && chatTab.classList.contains('active')) {
                renderChatForEmail(freshEmail);
            } else {
                renderEmailCard(freshEmail);
            }
        }

        alert("Данные сохранены");
    } catch (e) {
        console.error(e);
        alert(e.message || "Ошибка");
    }
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
    const mySeq = ++refreshSeq;
    const prevId = selectedEmailId;
    const inChat = isChatTabActive();

    if (isMaterialInputProtected()) {
        pendingSilentRefresh = true;
        return;
    }

    await loadEmailsFromApi(false);

    if (mySeq !== refreshSeq) {
        return;
    }

    renderEmailList();

    const currentEmail = prevId ? emails.find(e => e.id === prevId) : null;

    if (currentEmail) {
        highlightSelectedEmail(prevId);

        if (inChat) {
            if (isMaterialInputProtected()) {
                pendingSilentRefresh = true;
            } else {
                renderChatForEmail(currentEmail);
            }
        } else {
            renderEmailCard(currentEmail);
        }
    } else {
        if (inChat) {
            if (isMaterialInputProtected()) {
                pendingSilentRefresh = true;
            } else {
                renderChatForEmail(null);
            }
        }
    }

    const submitContainer = document.querySelector('.chat-submit');
    if (submitContainer) {
        submitContainer.style.display = emails.length === 0 ? 'none' : '';
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