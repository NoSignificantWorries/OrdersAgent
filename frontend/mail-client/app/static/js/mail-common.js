// ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
let emails = [];
let selectedEmailId = null;

const {
    formatDate,
    formatDateTime,
    escapeHtml,
    escapeAttr,
    mapTaskStatusToUiStatus,
    getStatusName,
} = window.MailFormatters;

const {
    downloadBlob,
    downloadEmailAttachments,
    loadAvailableResultDocuments,
    downloadAvailableResultDocuments,
    loadEmailsFromApi: loadEmailsFromApiFromApiModule,
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
    selectEmail: selectEmailFromModule,
} = window.MailRenderList;

const {
    getDisplayDocuments: getDisplayDocumentsFromModule,
    canCloseTask: canCloseTaskFromModule,
    renderEmailCard: renderEmailCardFromModule,
} = window.MailRenderCard;

const {
    initTabs: initTabsFromModule,
    refreshEmailsSilently: refreshEmailsSilentlyFromModule,
    initMailPage: initMailPageFromModule,
} = window.MailInit;

const chatStorage = new Map();

let currentStatusFilter = "all";
let currentClassFilter = "all";
let sortNewestFirst = true;
let currentSearchTerm = "";

let isMaterialInputComposing = false;
let pendingSilentRefresh = false;
let refreshSeq = 0;

// ========== КОНФИГУРАЦИЯ ==========
const decisionOptions = [
    { value: "", label: "Выберите класс" },
    { value: "request", label: "Заявка" },
    { value: "calculation", label: "Расчёт" },
    { value: "question", label: "Вопрос" },
];


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

        archived: item.archived === true,

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
    const result = await loadEmailsFromApiFromApiModule(
        showLoadingState,
        normalizeApiItem,
    );

    emails = result.emails || [];
    return result.ok;
}


// ========== ОТРИСОВКА СПИСКА ==========
function getMailRenderListState() {
    return {
        get emails() {
            return emails;
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
        get currentStatusFilter() {
            return currentStatusFilter;
        },
        get currentClassFilter() {
            return currentClassFilter;
        },
        get sortNewestFirst() {
            return sortNewestFirst;
        },
    };
}

function showLoading() {
    return showLoadingFromModule();
}

function highlightSelectedEmail(id) {
    return highlightSelectedEmailFromModule(id);
}

function renderEmailList() {
    return renderEmailListFromModule({
        state: getMailRenderListState(),
        escapeHtml,
        formatDate,
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
        chatStorage,
    };
}

function getDisplayDocuments(email) {
    return getDisplayDocumentsFromModule(email);
}

function canCloseTask(email) {
    return canCloseTaskFromModule(email);
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
        renderEmailList,
        highlightSelectedEmail,
        selectEmail,
    });
}


// ========== ЧАТ ==========
function isMaterialInputProtected() {
    return isMaterialInputProtectedFromModule({
        isMaterialInputComposing,
    });
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
        loadEmailsFromApi,
        renderEmailList,
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
        selectEmail,
        initTabs,
        sendChatData,
        isChatTabActive,
        isMaterialInputProtected,
        highlightSelectedEmail,
        renderChatForEmail,
        renderEmailCard,
    });
}

window.MailPage = {
    initMailPage,
};