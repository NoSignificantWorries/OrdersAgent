// ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
let allEmails = [];
let emails = [];
let selectedEmailId = null;
let selectedSourceType = "inbox";
let unreadCount = 0;
let selectedEmailSnapshot = null;

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
    loadForwardDraft,
    sendForwardEmail,
    getMySignature,
    updateMySignature,
    getEmailComment,
    updateEmailComment,
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
    syncInboxSelectionState: syncInboxSelectionStateFromModule,
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
    openForwardCompose: openForwardComposeFromModule,
    closeCompose: closeComposeFromModule,
    isComposeInputProtected: isComposeInputProtectedFromModule,
    initCompose: initComposeFromModule,
    appendSignatureIfMissing: appendSignatureIfMissingFromModule,
    ensureUserSignature: ensureUserSignatureFromModule,
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
let isCommentModalOpen = false;
let isCommentModalSaving = false;
const openReplyForms = new Set();
const expandedThreads = new Set();
let composeDraft = {
    isOpen: false,
    mode: "new",
    emailId: null,
    to: "",
    subject: "",
    body: "",
    files: [],
    sourceAttachments: [],
    selectedDocumentIds: [],
    isSending: false,
    isFocused: false,
    isComposing: false,
    isFileDialogOpen: false,
};

let userSignature = "";
let signatureLoaded = false;

let signatureModalOpen = false;
let signatureModalSaving = false;
let signatureDraft = "";

let mailToastTimer = null;

function syncInboxSelectionState(mode = "replace") {
    if (typeof syncInboxSelectionStateFromModule === "function") {
        return syncInboxSelectionStateFromModule(getMailRenderListState(), mode);
    }
}

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

function escapeSignatureHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function renderSignatureModal() {
    const root = document.getElementById("signature-modal-root");

    if (!root) return;

    root.innerHTML = `
        <div class="signature-modal-overlay ${signatureModalOpen ? "is-open" : ""}" ${signatureModalOpen ? "" : "hidden"}>
            <div class="signature-modal-backdrop" data-signature-close="backdrop"></div>
            <div
                class="signature-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="signature-modal-title"
            >
                <div class="signature-modal-header">
                    <h2 id="signature-modal-title" class="signature-modal-title">Подпись</h2>
                    <button
                        type="button"
                        class="signature-modal-close-btn"
                        data-signature-close="button"
                        aria-label="Закрыть окно"
                        title="Закрыть"
                        ${signatureModalSaving ? "disabled" : ""}
                    >
                        ×
                    </button>
                </div>

                <div class="signature-modal-body">
                    <label for="signature-textarea" class="signature-modal-label">
                        Текст подписи
                    </label>
                    <textarea
                        id="signature-textarea"
                        class="signature-modal-textarea"
                        placeholder="Введите подпись, которая будет подставляться в письмо"
                        ${signatureModalSaving ? "disabled" : ""}
                    >${escapeSignatureHtml(signatureDraft)}</textarea>
                    <div class="signature-modal-hint">
                        Подпись будет автоматически добавляться в новые письма, ответы и пересылки.
                    </div>
                </div>

                <div class="signature-modal-footer">
                    <button
                        type="button"
                        id="signature-cancel-btn"
                        class="signature-modal-secondary-btn"
                        ${signatureModalSaving ? "disabled" : ""}
                    >
                        Отмена
                    </button>
                    <button
                        type="button"
                        id="signature-save-btn"
                        class="signature-modal-primary-btn"
                        ${signatureModalSaving ? "disabled" : ""}
                    >
                        ${signatureModalSaving ? "Сохранение..." : "Сохранить"}
                    </button>
                </div>
            </div>
        </div>
    `;

    bindSignatureModalEvents();
}

async function openSignatureModal() {
    try {
        if (!signatureLoaded) {
            userSignature = await getMySignature();
            signatureLoaded = true;
        }

        signatureDraft = userSignature || "";
        signatureModalOpen = true;
        renderSignatureModal();

        const textarea = document.getElementById("signature-textarea");
        if (textarea) {
            textarea.focus();
        }
    } catch (error) {
        console.error(error);
        alert(error.message || "Не удалось загрузить подпись");
    }
}

function closeSignatureModal() {
    signatureModalOpen = false;
    signatureModalSaving = false;
    renderSignatureModal();
}

async function saveSignatureModal() {
    const textarea = document.getElementById("signature-textarea");
    if (!textarea) return;

    signatureDraft = textarea.value;

    try {
        signatureModalSaving = true;
        renderSignatureModal();

        const result = await updateMySignature(signatureDraft);

        userSignature = String(result?.signature || "");
        signatureDraft = userSignature;
        signatureLoaded = true;
        signatureModalSaving = false;
        signatureModalOpen = false;
        renderSignatureModal();

        showMailToast("Подпись сохранена");
    } catch (error) {
        console.error(error);
        signatureModalSaving = false;
        renderSignatureModal();
        alert(error.message || "Не удалось сохранить подпись");
    }
}

function bindSignatureModalEvents() {
    const openBtn = document.getElementById("signature-settings-btn");
    if (openBtn && !openBtn.dataset.signatureBound) {
        openBtn.dataset.signatureBound = "true";
        openBtn.addEventListener("click", () => {
            openSignatureModal();
        });
    }

    if (!document.body.dataset.signatureEscapeBound) {
        document.body.dataset.signatureEscapeBound = "true";
        document.addEventListener("keydown", handleSignatureModalEscape);
    }

    const overlay = document.querySelector(".signature-modal-overlay");
    const cancelBtn = document.getElementById("signature-cancel-btn");
    const saveBtn = document.getElementById("signature-save-btn");
    const textarea = document.getElementById("signature-textarea");

    if (textarea) {
        textarea.addEventListener("input", (event) => {
            signatureDraft = event.target.value;
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener("click", () => {
            if (signatureModalSaving) return;
            closeSignatureModal();
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener("click", async () => {
            if (signatureModalSaving) return;
            await saveSignatureModal();
        });
    }

    if (overlay) {
        overlay.addEventListener("click", (event) => {
            const closeTrigger = event.target.closest("[data-signature-close]");
            if (!closeTrigger) return;
            if (signatureModalSaving) return;
            closeSignatureModal();
        });
    }
}

function handleSignatureModalEscape(event) {
    if (event.key !== "Escape") return;
    if (!signatureModalOpen) return;
    if (signatureModalSaving) return;

    closeSignatureModal();
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

    const source = Array.isArray(allEmails) && allEmails.length ? allEmails : emails;

    const related = source.filter((email) => {
        const messageId = getEmailMessageId(email);
        const inReplyTo = getEmailInReplyTo(email);
        const refs = getEmailReferences(email);

        if (messageId && threadKeys.has(messageId)) return true;
        if (inReplyTo && threadKeys.has(inReplyTo)) return true;
        return refs.some((ref) => threadKeys.has(ref));
    });

    const currentRealId = Number(currentEmail.email_id || currentEmail.id || 0);

    if (
        !related.some((email) => Number(email.email_id || email.id) === Number(currentRealId))
    ) {
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
        comment_text: item.comment_text ?? null,
        has_comment: item.has_comment === true || Boolean(String(item.comment_text || "").trim()),


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

function normalizeSingleInboxDetailItem(item) {
    return normalizeApiItem(item, 0);
}

// ========== ЗАГРУЗКА ПИСЕМ ИЗ API ==========
async function loadEmailsFromApi(options = {}) {
    const normalizedOptions =
        typeof options === "object" && options !== null
            ? options
            : { showLoadingState: Boolean(options) };

    const result = await loadEmailsFromApiFromApiModule({
        ...normalizedOptions,
        normalizeApiItem,
    });

    allEmails = result.emails || [];
    emails = [...allEmails];
    recalculateUnreadCount();
    return result;
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
        get selectedEmailSnapshot() {
            return selectedEmailSnapshot;
        },
        set selectedEmailSnapshot(value) {
            selectedEmailSnapshot = value;
        },
        get selectedSourceType() {
            return selectedSourceType;
        },
        set selectedSourceType(value) {
            selectedSourceType = value;
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

function selectEmail(id, options = {}) {
    return selectEmailFromModule(
        id,
        {
            state: getMailRenderListState(),
            showLoading,
            highlightSelectedEmail,
            renderEmailCard,
            renderChatForEmail,
            renderEmailList,
            updateUnreadCount,
            normalizeInboxDetailItem: normalizeSingleInboxDetailItem,
        },
        options,
    );
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
        get selectedEmailSnapshot() {
            return selectedEmailSnapshot;
        },
        set selectedEmailSnapshot(value) {
            selectedEmailSnapshot = value;
        },
        get selectedSourceType() {
            return selectedSourceType;
        },
        set selectedSourceType(value) {
            selectedSourceType = value;
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
        get isCommentModalOpen() {
            return isCommentModalOpen;
        },
        set isCommentModalOpen(value) {
            isCommentModalOpen = value;
        },
        get isCommentModalSaving() {
            return isCommentModalSaving;
        },
        set isCommentModalSaving(value) {
            isCommentModalSaving = value;
        },
        get isReplyFileDialogOpen() {
            return isReplyFileDialogOpen;
        },
        set isReplyFileDialogOpen(value) {
            isReplyFileDialogOpen = value;
        },
        get userSignature() {
            return userSignature;
        },
        set userSignature(value) {
            userSignature = typeof value === "string" ? value : "";
        },
        get _signatureLoaded() {
            return signatureLoaded;
        },
        set _signatureLoaded(value) {
            signatureLoaded = value === true;
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

function closeOpenedEmail(options = {}) {
    return closeOpenedEmailFromModule(
        {
            state: getMailRenderListState(),
        },
        options,
    );
}

function closeAndMarkUnread() {
    return closeAndMarkUnreadFromModule({
        state: getMailRenderListState(),
        renderEmailList,
        updateUnreadCount,
    });
}

async function renderEmailCard(email) {
    return await renderEmailCardFromModule(email, {
        state: getMailRenderCardState(),
        escapeHtml,
        formatDate,
        formatTimeOnly,
        formatDateTime,
        getStatusName,
        decisionOptions,
        mapTaskStatusToUiStatus,
        downloadEmailAttachments,
        getDisplayDocuments,
        canCloseTask,
        canUnarchiveTask,
        renderEmailList,
        updateUnreadCount,
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

function isCommentModalProtected() {
    return isCommentModalOpen === true || isCommentModalSaving === true;
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
        get userSignature() {
            return userSignature;
        },
        set userSignature(value) {
            userSignature = typeof value === "string" ? value : "";
        },
        get _signatureLoaded() {
            return signatureLoaded;
        },
        set _signatureLoaded(value) {
            signatureLoaded = value === true;
        },
    };
}

function appendSignatureIfMissing(body, signature) {
    if (typeof appendSignatureIfMissingFromModule === "function") {
        return appendSignatureIfMissingFromModule(body, signature);
    }
    return String(body || "").trim();
}

async function ensureUserSignature(state = getMailComposeState()) {
    if (typeof ensureUserSignatureFromModule === "function") {
        return ensureUserSignatureFromModule(state);
    }
    return "";
}

function renderCompose() {
    return renderComposeFromModule({
        state: getMailComposeState(),
    });
}

async function openForwardCompose(payload) {
    return openForwardComposeFromModule(
        {
            state: getMailComposeState(),
            loadForwardDraft,
            renderCompose,
        },
        payload,
    );
}

function initCompose() {
    return initComposeFromModule({
        state: getMailComposeState(),
        sendNewEmail,
        loadForwardDraft,
        sendForwardEmail,
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
            get selectedSourceType() {
                return selectedSourceType;
            },
            set selectedSourceType(value) {
                selectedSourceType = value;
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
        get selectedEmailSnapshot() {
            return selectedEmailSnapshot;
        },
        set selectedEmailSnapshot(value) {
            selectedEmailSnapshot = value;
        },
        get selectedSourceType() {
            return selectedSourceType;
        },
        set selectedSourceType(value) {
            selectedSourceType = value;
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
        get isCommentModalOpen() {
            return isCommentModalOpen;
        },
        set isCommentModalOpen(value) {
            isCommentModalOpen = value;
        },
        get isCommentModalSaving() {
            return isCommentModalSaving;
        },
        set isCommentModalSaving(value) {
            isCommentModalSaving = value;
        },
        get isReplyFileDialogOpen() {
            return isReplyFileDialogOpen;
        },
        set isReplyFileDialogOpen(value) {
            isReplyFileDialogOpen = value;
        },
        get userSignature() {
            return userSignature;
        },
        set userSignature(value) {
            userSignature = typeof value === "string" ? value : "";
        },
        get _signatureLoaded() {
            return signatureLoaded;
        },
        set _signatureLoaded(value) {
            signatureLoaded = value === true;
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
        isDecisionSelectProtected,
        isCommentModalProtected,
        loadEmailsFromApi,
        renderEmailList,
        updateUnreadCount,
        highlightSelectedEmail,
        renderChatForEmail,
        renderEmailCard,
    });
}

function initSignatureSettings() {
    renderSignatureModal();
}

function initMailPage(config) {
    initSignatureSettings();

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
        isCommentModalProtected,
        highlightSelectedEmail,
        renderChatForEmail,
        renderEmailCard,
    });
}

window.MailPage = {
    initMailPage,
    showMailToast,
    openForwardCompose,
    openSignatureModal,
    initSignatureSettings,
};