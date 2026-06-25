// ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
let emails = [];
let selectedEmailId = null;
let unreadCount = 0;

// ========== ПАГИНАЦИЯ ==========
const PAGE_SIZE = 100;          // фиксированный размер страницы
let currentPage = 0;
let totalEmails = 0;

const {
    formatDate,
    formatDateTime,
    formatTimeOnly,
    escapeHtml,
    escapeAttr,
    mapTaskStatusToUiStatus,
    getStatusName,
    formatUnreadCount,
} = window.MailFormatters;

const {
    downloadBlob,
    downloadEmailAttachments,
    loadAvailableResultDocuments,
    downloadAvailableResultDocuments,
    loadEmailsFromApi: loadEmailsFromApiFromApiModule,
    sendNewEmail,
} = window.MailApi;

const {
    extractMaterialNames,
    extractMaterialsFromOutput,
    buildChatItemsFromOutput,
    isEditingMaterialInput,
    isChatTabActive,
    isMaterialInputProtected: isMaterialInputProtectedFromModule,
    bindMaterialInputEvents,
    renderChatForEmail: renderChatForEmailFromModule,
    sendChatData: sendChatDataFromModule,
} = window.MailChat;

const {
    showLoading: showLoadingFromModule,
    highlightSelectedEmail: highlightSelectedEmailFromModule,
    renderEmailList: renderEmailListFromModule,
    updateUnreadCount: updateUnreadCountFromModule,
    selectEmail: selectEmailFromModule,
    closeOpenedEmail: closeOpenedEmailFromModule,
    closeAndMarkUnread: closeAndMarkUnreadFromModule,
} = window.MailRenderList;

const {
    getDisplayDocuments: getDisplayDocumentsFromModule,
    canCloseTask: canCloseTaskFromModule,
    canUnarchiveTask: canUnarchiveTaskFromModule,
    renderEmailCard: renderEmailCardFromModule,
    isReplyInputProtected: isReplyInputProtectedFromModule,
} = window.MailRenderCard;

const {
    initTabs: initTabsFromModule,
    refreshEmailsSilently: refreshEmailsSilentlyFromModule,
    initMailPage: initMailPageFromModule,
} = window.MailInit;

const {
    ensureComposeState: ensureComposeStateFromModule,
    renderCompose: renderComposeFromModule,
    openCompose: openComposeFromModule,
    closeCompose: closeComposeFromModule,
    isComposeInputProtected: isComposeInputProtectedFromModule,
    initCompose: initComposeFromModule,
} = window.MailCompose;

const chatStorage = new Map();

let currentStatusFilter = "all";
let currentClassFilter = "all";
let sortNewestFirst = true;
let currentSearchTerm = "";

let isMaterialInputComposing = false;
let pendingSilentRefresh = false;
let refreshSeq = 0;
let isReplyInputComposing = false;
const replyDrafts = new Map();
let isReplyInputFocused = false;
let isReplyFileDialogOpen = false;
let isDecisionSelectFocused = false;
const openReplyForms = new Set();
const expandedThreads = new Set();
let composeDraft = {
    isOpen: false,
    to: "",
    subject: "",
    body: "",
    files: [],
    isSending: false,
    isFocused: false,
    isComposing: false,
    isFileDialogOpen: false,
};

let mailToastTimer = null;

function showMailToast(message) {
    const toast = document.getElementById("mail-toast");
    if (!toast) return;

    toast.textContent = message;
    toast.classList.add("is-visible");

    if (mailToastTimer) {
        clearTimeout(mailToastTimer);
    }

    mailToastTimer = setTimeout(() => {
        toast.classList.remove("is-visible");
        toast.textContent = "";
    }, 2800);
}

function normalizeHeaderValue(value) {
    return String(value || "").trim();
}

function normalizeReferences(value) {
    if (Array.isArray(value)) {
        return value.map((item) => normalizeHeaderValue(item)).filter(Boolean);
    }

    return normalizeHeaderValue(value)
        .split(/\s+/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function getEmailMessageId(email) {
    return normalizeHeaderValue(
        email?.message_id || email?.messageId || email?.messageid
    );
}

function getEmailInReplyTo(email) {
    return normalizeHeaderValue(
        email?.in_reply_to || email?.inReplyTo || email?.inreplyto
    );
}

function getEmailReferences(email) {
    return normalizeReferences(
        email?.references || email?.email_references || email?.refs
    );
}

function getThreadMessages(currentEmail) {
    if (!currentEmail) return [];

    const currentMessageId = getEmailMessageId(currentEmail);
    const currentInReplyTo = getEmailInReplyTo(currentEmail);
    const currentReferences = getEmailReferences(currentEmail);

    const threadKeys = new Set(
        [currentMessageId, currentInReplyTo, ...currentReferences].filter(Boolean)
    );

    if (!threadKeys.size) {
        return [currentEmail];
    }

    const related = emails.filter((email) => {
        const messageId = getEmailMessageId(email);
        const inReplyTo = getEmailInReplyTo(email);
        const refs = getEmailReferences(email);

        if (messageId && threadKeys.has(messageId)) return true;
        if (inReplyTo && threadKeys.has(inReplyTo)) return true;
        return refs.some((ref) => threadKeys.has(ref));
    });

    if (!related.some((email) => email.id === currentEmail.id)) {
        related.push(currentEmail);
    }

    related.sort((a, b) => new Date(a.date) - new Date(b.date));
    return related;
}

function isThreadExpanded(emailId) {
    return expandedThreads.has(Number(emailId));
}

function toggleThreadExpanded(emailId) {
    const normalizedId = Number(emailId);
    if (expandedThreads.has(normalizedId)) {
        expandedThreads.delete(normalizedId);
    } else {
        expandedThreads.add(normalizedId);
    }
}

// ========== КОНФИГУРАЦИЯ ==========
const decisionOptions = [
    { value: "", label: "Выберите класс" },
    { value: "request", label: "Заявка" },
    { value: "calculation", label: "Расчёт" },
    { value: "question", label: "Вопрос" },
];

function recalculateUnreadCount() {
    unreadCount = emails.reduce((acc, email) => {
        return acc + (email.archived !== true && email.read !== true ? 1 : 0);
    }, 0);
}

// ========== НОРМАЛИЗАЦИЯ ДАННЫХ API ==========
function normalizeApiItem(item, idx) {
    const output =
        item.outputdata && typeof item.outputdata === "object"
            ? item.outputdata
            : {};
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
        message_id: item.messageid || item.message_id || null,
        in_reply_to: item.inreplyto || item.in_reply_to || null,
        references: Array.isArray(item.references)
            ? item.references
            : (item.references || item.emailreferences || ""),

        archived: item.archived === true,
        read: item.is_read === true,

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
            completed_at: item.taskcompletedat || null,
        },

        task_status: taskStatus,
        status: uiStatus,

        documents,
        document_names: documents
            .map((doc) => doc?.document_name)
            .filter((name) => name && String(name).trim() !== ""),
    };

    normalized.chatItems = buildChatItemsFromOutput(
        output,
        normalized.id,
        chatStorage,
    );
    chatStorage.set(normalized.id, normalized.chatItems);

    return normalized;
}


// ========== ЗАГРУЗКА ПИСЕМ ИЗ API ==========
async function loadEmailsFromApi(showLoadingState = true) {
    const cfg = window.MAILPAGECONFIG || {};
    const baseUrl = cfg.apiUrl || "/api/queue";
    const url = new URL(baseUrl, window.location.origin);
    url.searchParams.set('offset', currentPage * PAGE_SIZE);
    url.searchParams.set('limit', PAGE_SIZE);

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

        const resp = await fetch(url, {
            method: "GET",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });

        if (resp.status === 401) {
            if (countSpan) countSpan.textContent = "Не авторизован";
            if (listEl) {
                listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Нужно войти заново</div>`;
            }
            if (viewEl) {
                viewEl.innerHTML = `<div class="email-placeholder">Нужно войти заново</div>`;
            }
            return false;
        }

        if (!resp.ok) {
            if (countSpan) countSpan.textContent = "Ошибка";
            if (listEl) {
                listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
            }
            if (viewEl) {
                viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
            }
            return false;
        }

        const data = await resp.json();
        const items = Array.isArray(data.items) ? data.items : [];
        totalEmails = data.total || 0;

        emails = items.map((item, idx) => normalizeApiItem(item, idx));
        recalculateUnreadCount();

        // Обновляем счётчик
        if (countSpan) {
            const pageType = cfg.pageType || "inbox";
            if (pageType === "archived") {
                countSpan.textContent = `${emails.length} из ${totalEmails}`;
            } else {
                countSpan.textContent = `${emails.length} из ${totalEmails} (непрочитанных: ${unreadCount})`;
            }
        }

        renderPagination(); // отрисовать элементы управления
        return true;
    } catch (e) {
        console.error("Ошибка загрузки писем:", e);
        const listEl = document.getElementById("emailsContainer");
        const viewEl = document.getElementById("emailView");
        const countSpan = document.getElementById("email-count-display");
        if (countSpan) countSpan.textContent = "Ошибка";
        if (listEl) {
            listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
        }
        if (viewEl) {
            viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
        }
        return false;
    }
}

// ========== ПАГИНАЦИЯ: ОТРИСОВКА И ПЕРЕЗАГРУЗКА ==========
function renderPagination() {
    const container = document.getElementById('pagination-controls');
    if (!container) return;
    const totalPages = Math.ceil(totalEmails / PAGE_SIZE) || 1;
    const current = currentPage + 1;

    const prevBtn = document.getElementById('prev-page-btn');
    const nextBtn = document.getElementById('next-page-btn');
    const pageInfo = document.getElementById('page-info');

    if (prevBtn) {
        prevBtn.disabled = currentPage === 0;
        prevBtn.onclick = () => {
            if (currentPage > 0) {
                currentPage--;
                reloadPage();
            }
        };
    }

    if (nextBtn) {
        nextBtn.disabled = currentPage >= totalPages - 1;
        nextBtn.onclick = () => {
            if (currentPage < totalPages - 1) {
                currentPage++;
                reloadPage();
            }
        };
    }

    if (pageInfo) {
        pageInfo.textContent = `Страница ${current} из ${totalPages}`;
    }
}

function reloadPage() {
    loadEmailsFromApi(true).then(() => {
        renderEmailList();
        selectedEmailId = null;
        const emailView = document.getElementById('emailView');
        if (emailView) {
            emailView.innerHTML = '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
        }
    });
}

// ========== ОТРИСОВКА СПИСКА ==========
function getMailRenderListState() {
    return {
        get emails() {
            return emails;
        },
        set emails(value) {
            emails = value;
        },

        get selectedEmailId() {
            return selectedEmailId;
        },
        set selectedEmailId(value) {
            selectedEmailId = value;
        },

        get currentSearchTerm() {
            return currentSearchTerm;
        },
        set currentSearchTerm(value) {
            currentSearchTerm = value;
        },

        get currentStatusFilter() {
            return currentStatusFilter;
        },
        set currentStatusFilter(value) {
            currentStatusFilter = value;
        },

        get currentClassFilter() {
            return currentClassFilter;
        },
        set currentClassFilter(value) {
            currentClassFilter = value;
        },

        get sortNewestFirst() {
            return sortNewestFirst;
        },
        set sortNewestFirst(value) {
            sortNewestFirst = value;
        },

        get unreadCount() {
            return unreadCount;
        },
        set unreadCount(value) {
            unreadCount = value;
        },

        openReplyForms,
    };
}

function showLoading() {
    return showLoadingFromModule();
}

function highlightSelectedEmail(id) {
    return highlightSelectedEmailFromModule(id);
}

function updateUnreadCount() {
    return updateUnreadCountFromModule({
        state: getMailRenderListState(),
        formatUnreadCount,
    });
}

function renderEmailList() {
    return renderEmailListFromModule({
        state: getMailRenderListState(),
        escapeHtml,
        formatDate,
        formatTimeOnly,
        getStatusName,
        selectEmail,
    });
}

function selectEmail(id) {
    return selectEmailFromModule(id, {
        state: getMailRenderListState(),
        showLoading,
        highlightSelectedEmail,
        renderEmailCard,
        renderChatForEmail,
        renderEmailList,
        updateUnreadCount,
    });
}


// ========== КАРТОЧКА ПИСЬМА ==========
function getMailRenderCardState() {
    return {
        get emails() {
            return emails;
        },
        set emails(value) {
            emails = value;
        },
        get selectedEmailId() {
            return selectedEmailId;
        },
        set selectedEmailId(value) {
            selectedEmailId = value;
        },
        get pendingSilentRefresh() {
            return pendingSilentRefresh;
        },
        set pendingSilentRefresh(value) {
            pendingSilentRefresh = value;
        },
        get isReplyInputComposing() {
            return isReplyInputComposing;
        },
        set isReplyInputComposing(value) {
            isReplyInputComposing = value;
        },
        get isReplyInputFocused() {
            return isReplyInputFocused;
        },
        set isReplyInputFocused(value) {
            isReplyInputFocused = value;
        },
        get isDecisionSelectFocused() {
            return isDecisionSelectFocused;
        },
        set isDecisionSelectFocused(value) {
            isDecisionSelectFocused = value;
        },
        get isReplyFileDialogOpen() {
            return isReplyFileDialogOpen;
        },
        set isReplyFileDialogOpen(value) {
            isReplyFileDialogOpen = value;
        },
        replyDrafts,
        chatStorage,
        openReplyForms,
        expandedThreads,
    };
}

function getDisplayDocuments(email) {
    return getDisplayDocumentsFromModule(email);
}

function canCloseTask(email) {
    return canCloseTaskFromModule(email);
}

function canUnarchiveTask(email) {
    return canUnarchiveTaskFromModule(email);
}

function closeOpenedEmail() {
    return closeOpenedEmailFromModule({
        state: getMailRenderListState(),
    });
}

function closeAndMarkUnread() {
    return closeAndMarkUnreadFromModule({
        state: getMailRenderListState(),
        renderEmailList,
        updateUnreadCount,
    });
}

function renderEmailCard(email) {
    return renderEmailCardFromModule(email, {
        state: getMailRenderCardState(),
        escapeHtml,
        formatDateTime,
        getStatusName,
        decisionOptions,
        mapTaskStatusToUiStatus,
        downloadEmailAttachments,
        getDisplayDocuments,
        canCloseTask,
        canUnarchiveTask,
        renderEmailList,
        highlightSelectedEmail,
        selectEmail,
        closeOpenedEmail,
        closeAndMarkUnread,
        refreshEmailsSilently,
        getThreadMessages,
        isThreadExpanded,
        toggleThreadExpanded,
    });
}


// ========== ЧАТ ==========
function isMaterialInputProtected() {
    return isMaterialInputProtectedFromModule({
        isMaterialInputComposing,
    });
}

function isReplyInputProtected(state) {
    const selectedId = state.selectedEmailId;

    return (
        state.isReplyInputFocused === true ||
        state.isReplyInputComposing === true ||
        state.isReplyFileDialogOpen === true ||
        (selectedId != null && state.openReplyForms?.has(selectedId) === true)
    );
}

function isDecisionSelectProtected() {
    return isDecisionSelectFocused === true;
}

function getMailComposeState() {
    return {
        get composeDraft() {
            return composeDraft;
        },
        set composeDraft(value) {
            composeDraft = value;
        },
        get pendingSilentRefresh() {
            return pendingSilentRefresh;
        },
        set pendingSilentRefresh(value) {
            pendingSilentRefresh = value;
        },
    };
}

function renderCompose() {
    return renderComposeFromModule({
        state: getMailComposeState(),
    });
}

function initCompose() {
    return initComposeFromModule({
        state: getMailComposeState(),
        sendNewEmail,
    });
}

function isComposeInputProtected() {
    return isComposeInputProtectedFromModule(getMailComposeState());
}

function getMailChatDeps() {
    return {
        state: {
            get emails() {
                return emails;
            },
            set emails(value) {
                emails = value;
            },
            get selectedEmailId() {
                return selectedEmailId;
            },
            set selectedEmailId(value) {
                selectedEmailId = value;
            },
            chatStorage,
            get isMaterialInputComposing() {
                return isMaterialInputComposing;
            },
            set isMaterialInputComposing(value) {
                isMaterialInputComposing = value;
            },
            get pendingSilentRefresh() {
                return pendingSilentRefresh;
            },
            set pendingSilentRefresh(value) {
                pendingSilentRefresh = value;
            },
        },
        escapeHtml,
        loadAvailableResultDocuments,
        downloadAvailableResultDocuments,
        loadEmailsFromApi,
        renderEmailList,
        renderEmailCard,
        highlightSelectedEmail,
        refreshEmailsSilently,
        bindMaterialInputEvents,
        renderChatForEmail: (email) =>
            renderChatForEmailFromModule(email, getMailChatDeps()),
    };
}

function renderChatForEmail(email) {
    return renderChatForEmailFromModule(email, getMailChatDeps());
}

function sendChatData() {
    return sendChatDataFromModule(getMailChatDeps());
}


// ========== ИНИЦИАЛИЗАЦИЯ ==========
function getMailInitState() {
    return {
        get emails() {
            return emails;
        },
        set emails(value) {
            emails = value;
        },
        get selectedEmailId() {
            return selectedEmailId;
        },
        set selectedEmailId(value) {
            selectedEmailId = value;
        },
        chatStorage,
        replyDrafts,
        openReplyForms, 
        get composeDraft() {
            return composeDraft;
        },
        set composeDraft(value) {
            composeDraft = value;
        },
        get currentSearchTerm() {
            return currentSearchTerm;
        },
        set currentSearchTerm(value) {
            currentSearchTerm = value;
        },
        get currentStatusFilter() {
            return currentStatusFilter;
        },
        set currentStatusFilter(value) {
            currentStatusFilter = value;
        },
        get currentClassFilter() {
            return currentClassFilter;
        },
        set currentClassFilter(value) {
            currentClassFilter = value;
        },
        get sortNewestFirst() {
            return sortNewestFirst;
        },
        set sortNewestFirst(value) {
            sortNewestFirst = value;
        },
        get isMaterialInputComposing() {
            return isMaterialInputComposing;
        },
        set isMaterialInputComposing(value) {
            isMaterialInputComposing = value;
        },
        get isReplyInputComposing() {
            return isReplyInputComposing;
        },
        set isReplyInputComposing(value) {
            isReplyInputComposing = value;
        },
        get pendingSilentRefresh() {
            return pendingSilentRefresh;
        },
        set pendingSilentRefresh(value) {
            pendingSilentRefresh = value;
        },
        get refreshSeq() {
            return refreshSeq;
        },
        set refreshSeq(value) {
            refreshSeq = value;
        },
        get isReplyInputFocused() {
            return isReplyInputFocused;
        },
        set isReplyInputFocused(value) {
            isReplyInputFocused = value;
        },
        get isDecisionSelectFocused() {
            return isDecisionSelectFocused;
        },
        set isDecisionSelectFocused(value) {
            isDecisionSelectFocused = value;
        },
        get isReplyFileDialogOpen() {
            return isReplyFileDialogOpen;
        },
        set isReplyFileDialogOpen(value) {
            isReplyFileDialogOpen = value;
        },
    };
}

function initTabs() {
    return initTabsFromModule({
        state: getMailInitState(),
        renderChatForEmail,
        renderEmailCard,
    });
}

function refreshEmailsSilently() {
    return refreshEmailsSilentlyFromModule({
        state: getMailInitState(),
        isChatTabActive,
        isMaterialInputProtected,
        isReplyInputProtected,
        isComposeInputProtected,
        loadEmailsFromApi,
        renderEmailList,
        updateUnreadCount,
        highlightSelectedEmail,
        renderChatForEmail,
        renderEmailCard,
    });
}

function initMailPage(config) {
    return initMailPageFromModule(config, {
        state: getMailInitState(),
        loadEmailsFromApi,
        renderEmailList,
        updateUnreadCount,
        selectEmail,
        initTabs,
        initCompose,
        sendChatData,
        isChatTabActive,
        isMaterialInputProtected,
        isReplyInputProtected,
        isComposeInputProtected,
        isDecisionSelectProtected,
        highlightSelectedEmail,
        renderChatForEmail,
        renderEmailCard,
    });
}

window.MailPage = {
    initMailPage,
    showMailToast,
};