(function () {
    const {
        sendNewEmail,
        loadForwardDraft,
        sendForwardEmail,
    } = window.MailApi || {};

    function ensureComposeState(state) {
        if (!state.composeDraft || typeof state.composeDraft !== "object") {
            state.composeDraft = {};
        }

        state.composeDraft.isOpen = state.composeDraft.isOpen === true;
        state.composeDraft.mode =
            state.composeDraft.mode === "forward" ? "forward" : "new";
        state.composeDraft.emailId =
            state.composeDraft.emailId == null ? null : Number(state.composeDraft.emailId);
        state.composeDraft.to = state.composeDraft.to || "";
        state.composeDraft.subject = state.composeDraft.subject || "";
        state.composeDraft.body = state.composeDraft.body || "";
        state.composeDraft.files = Array.isArray(state.composeDraft.files)
            ? state.composeDraft.files
            : [];
        state.composeDraft.sourceAttachments = Array.isArray(state.composeDraft.sourceAttachments)
            ? state.composeDraft.sourceAttachments
            : [];
        state.composeDraft.selectedDocumentIds = Array.isArray(state.composeDraft.selectedDocumentIds)
            ? state.composeDraft.selectedDocumentIds.map((id) => Number(id)).filter((id) => !Number.isNaN(id))
            : [];
        state.composeDraft.isSending = state.composeDraft.isSending === true;
        state.composeDraft.isFocused = state.composeDraft.isFocused === true;
        state.composeDraft.isComposing = state.composeDraft.isComposing === true;
        state.composeDraft.isFileDialogOpen =
            state.composeDraft.isFileDialogOpen === true;
    }

    function escapeComposeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function resetComposeDraft(state) {
        ensureComposeState(state);
        state.composeDraft.mode = "new";
        state.composeDraft.emailId = null;
        state.composeDraft.to = "";
        state.composeDraft.subject = "";
        state.composeDraft.body = "";
        state.composeDraft.files = [];
        state.composeDraft.sourceAttachments = [];
        state.composeDraft.selectedDocumentIds = [];
        state.composeDraft.isSending = false;
        state.composeDraft.isFocused = false;
        state.composeDraft.isComposing = false;
        state.composeDraft.isFileDialogOpen = false;
    }

    function renderComposeFiles(state) {
        ensureComposeState(state);

        const files = state.composeDraft.files || [];
        if (!files.length) {
            return '<div class="compose-files-empty">Вложения не выбраны</div>';
        }

        return `
            <div class="compose-files-list">
                ${files
                    .map(
                        (file, index) => `
                            <div class="compose-file-item">
                                <span class="compose-file-name" title="${escapeComposeHtml(file.name)}">
                                    ${escapeComposeHtml(file.name)}
                                </span>
                                <button
                                    type="button"
                                    class="compose-file-remove-btn"
                                    data-compose-file-remove="${index}"
                                    aria-label="Удалить файл ${escapeComposeHtml(file.name)}"
                                    title="Удалить файл"
                                >
                                    ×
                                </button>
                            </div>
                        `,
                    )
                    .join("")}
            </div>
        `;
    }

    function renderForwardSourceAttachments(state) {
        ensureComposeState(state);

        const docs = state.composeDraft.sourceAttachments || [];
        if (!docs.length) {
            return `
                <div class="compose-source-files-empty">
                    У исходного письма нет доступных вложений для пересылки
                </div>
            `;
        }

        const selectedIds = new Set(state.composeDraft.selectedDocumentIds || []);

        return `
            <div class="compose-source-files-list">
                ${docs
                    .map((doc, index) => {
                        const documentId = Number(doc.document_id ?? doc.id);
                        const checked = selectedIds.has(documentId);
                        const filename = escapeComposeHtml(
                            doc.filename || doc.document_name || `document-${index + 1}`
                        );
                        const contentType = escapeComposeHtml(doc.content_type || "");
                        const sizeBytes = Number(doc.size_bytes ?? 0);

                        return `
                            <label class="compose-source-file-item">
                                <input
                                    type="checkbox"
                                    class="compose-source-file-checkbox"
                                    data-compose-source-doc-id="${documentId}"
                                    ${checked ? "checked" : ""}
                                    ${state.composeDraft.isSending ? "disabled" : ""}
                                />
                                <span class="compose-source-file-meta">
                                    <span class="compose-source-file-name" title="${filename}">
                                        ${filename}
                                    </span>
                                    <span class="compose-source-file-details">
                                        ${contentType ? `${contentType}` : ""}
                                        ${sizeBytes > 0 ? `${contentType ? " • " : ""}${sizeBytes} байт` : ""}
                                    </span>
                                </span>
                            </label>
                        `;
                    })
                    .join("")}
            </div>
        `;
    }

    function renderCompose(deps) {
        const { state } = deps;
        ensureComposeState(state);

        const root = document.getElementById("compose-root");
        if (!root) return;

        const draft = state.composeDraft;
        const isVisible = draft.isOpen === true;

        const isForwardMode = draft.mode === "forward";
        const titleText = isForwardMode ? "Переслать письмо" : "Новое письмо";
        const submitText = draft.isSending
            ? (isForwardMode ? "Пересылка..." : "Отправка...")
            : (isForwardMode ? "Переслать" : "Отправить");

        root.innerHTML = `
            <div class="compose-overlay ${isVisible ? "is-open" : ""}" ${isVisible ? "" : "hidden"}>
                <div class="compose-backdrop" data-compose-close="backdrop"></div>
                <div
                    class="compose-modal"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="compose-title"
                >
                    <div class="compose-header">
                        <h2 id="compose-title" class="compose-title">${titleText}</h2>
                        <button
                            type="button"
                            class="compose-close-btn"
                            data-compose-close="button"
                            aria-label="Закрыть форму"
                            title="Закрыть"
                            ${draft.isSending ? "disabled" : ""}
                        >
                            ×
                        </button>
                    </div>

                    <div class="compose-body">
                        <label class="compose-field">
                            <span class="compose-label">Кому</span>
                            <input
                                type="text"
                                id="compose-to-input"
                                name="to"
                                class="compose-input"
                                placeholder="email1@example.com, email2@example.com"
                                value="${escapeComposeHtml(draft.to)}"
                                ${draft.isSending ? "disabled" : ""}
                            />
                        </label>

                        <label class="compose-field">
                            <span class="compose-label">Тема</span>
                            <input
                                type="text"
                                id="compose-subject-input"
                                name="subject"
                                class="compose-input"
                                placeholder="Тема письма"
                                value="${escapeComposeHtml(draft.subject)}"
                                ${draft.isSending ? "disabled" : ""}
                                ${isForwardMode ? "readonly" : ""}
                            />
                        </label>

                        <label class="compose-field">
                            <span class="compose-label">Сообщение</span>
                            <textarea
                                id="compose-body-input"
                                name="body"
                                class="compose-textarea"
                                placeholder="Введите текст письма"
                                ${draft.isSending ? "disabled" : ""}
                            >${escapeComposeHtml(draft.body)}</textarea>
                        </label>

                        ${
                            isForwardMode
                                ? `
                                    <div class="compose-field">
                                        <div class="compose-attachments-header">
                                            <span class="compose-label">Вложения исходного письма</span>
                                        </div>

                                        <div class="compose-source-files-container">
                                            ${renderForwardSourceAttachments(state)}
                                        </div>
                                    </div>
                                `
                                : ""
                        }

                        <div class="compose-field">
                            <div class="compose-attachments-header">
                                <span class="compose-label">Вложения</span>
                                <label class="compose-attach-btn">
                                    <input
                                        type="file"
                                        id="compose-file-input"
                                        multiple
                                        hidden
                                        ${draft.isSending ? "disabled" : ""}
                                    />
                                    Добавить файлы
                                </label>
                            </div>

                            <div id="compose-files-container" class="compose-files-container">
                                ${renderComposeFiles(state)}
                            </div>
                        </div>
                    </div>

                    <div class="compose-footer">
                        <button
                            type="button"
                            id="compose-cancel-btn"
                            class="compose-secondary-btn"
                            ${draft.isSending ? "disabled" : ""}
                        >
                            Отмена
                        </button>

                        <button
                            type="button"
                            id="compose-send-btn"
                            class="compose-primary-btn"
                            ${draft.isSending ? "disabled" : ""}
                        >
                            ${submitText}
                        </button>
                    </div>
                </div>
            </div>
        `;

        bindComposeEvents(deps);
    }

    function openCompose(deps, preset = {}) {
        const { state } = deps;
        ensureComposeState(state);

        resetComposeDraft(state);

        state.composeDraft.isOpen = true;
        state.composeDraft.mode = "new";

        if (typeof preset.to === "string") {
            state.composeDraft.to = preset.to;
        }
        if (typeof preset.subject === "string") {
            state.composeDraft.subject = preset.subject;
        }
        if (typeof preset.body === "string") {
            state.composeDraft.body = preset.body;
        }

        renderCompose(deps);

        const toInput = document.getElementById("compose-to-input");
        if (toInput) {
            toInput.focus();
        }
    }

    async function openForwardCompose(deps, payload = {}) {
        const { state } = deps;
        ensureComposeState(state);

        const emailId = Number(payload?.emailId);
        if (Number.isNaN(emailId)) {
            throw new Error("Некорректный идентификатор письма");
        }

        const loader =
            payload.loadForwardDraft ||
            deps.loadForwardDraft ||
            loadForwardDraft;

        if (typeof loader !== "function") {
            throw new Error("Метод загрузки черновика пересылки не подключен");
        }

        const draftData = await loader(emailId);
        const attachments = Array.isArray(draftData?.attachments)
            ? draftData.attachments
            : [];

        resetComposeDraft(state);

        state.composeDraft.isOpen = true;
        state.composeDraft.mode = "forward";
        state.composeDraft.emailId = emailId;
        state.composeDraft.to = typeof draftData?.to === "string" ? draftData.to : "";
        state.composeDraft.subject =
            typeof draftData?.subject === "string" ? draftData.subject : "";
        state.composeDraft.body = typeof draftData?.body === "string" ? draftData.body : "";
        state.composeDraft.files = [];
        state.composeDraft.sourceAttachments = attachments;
        state.composeDraft.selectedDocumentIds = attachments
            .filter((item) => item?.selected !== false)
            .map((item) => Number(item.document_id ?? item.id))
            .filter((id) => !Number.isNaN(id));

        renderCompose(deps);

        const toInput = document.getElementById("compose-to-input");
        if (toInput) {
            toInput.focus();
        }
    }

    function closeCompose(deps, { clear = false } = {}) {
        const { state } = deps;
        ensureComposeState(state);

        if (clear) {
            resetComposeDraft(state);
        }

        state.composeDraft.isOpen = false;
        state.composeDraft.isFocused = false;
        state.composeDraft.isComposing = false;
        state.composeDraft.isFileDialogOpen = false;

        renderCompose(deps);
    }

    function handleComposeInput(event, deps) {
        const { state } = deps;
        ensureComposeState(state);

        const target = event.target;
        if (!target || !target.name) return;

        if (target.name === "to") {
            state.composeDraft.to = target.value;
        } else if (target.name === "subject") {
            state.composeDraft.subject = target.value;
        } else if (target.name === "body") {
            state.composeDraft.body = target.value;
        }
    }

    function addComposeFiles(fileList, deps) {
        const { state } = deps;
        ensureComposeState(state);

        const files = Array.from(fileList || []);
        if (!files.length) return;

        state.composeDraft.files = [...state.composeDraft.files, ...files];
        renderCompose(deps);
    }

    function removeComposeFile(index, deps) {
        const { state } = deps;
        ensureComposeState(state);

        state.composeDraft.files = state.composeDraft.files.filter(
            (_, fileIndex) => fileIndex !== index,
        );

        renderCompose(deps);
    }

    function toggleForwardSourceAttachment(documentId, checked, deps) {
        const { state } = deps;
        ensureComposeState(state);

        const normalizedId = Number(documentId);
        if (Number.isNaN(normalizedId)) return;

        const selected = new Set(state.composeDraft.selectedDocumentIds || []);

        if (checked) {
            selected.add(normalizedId);
        } else {
            selected.delete(normalizedId);
        }

        state.composeDraft.selectedDocumentIds = Array.from(selected);
    }

    function parseRecipients(value) {
        return String(value || "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function validateComposeDraft(state) {
        ensureComposeState(state);

        const recipients = parseRecipients(state.composeDraft.to);
        if (!recipients.length) {
            throw new Error("Укажите хотя бы одного получателя");
        }

        if (!String(state.composeDraft.body || "").trim()) {
            throw new Error("Введите текст письма");
        }

        return {
            mode: state.composeDraft.mode === "forward" ? "forward" : "new",
            emailId:
                state.composeDraft.emailId == null
                    ? null
                    : Number(state.composeDraft.emailId),
            recipients,
            subject: String(state.composeDraft.subject || "").trim(),
            body: String(state.composeDraft.body || "").trim(),
            selectedDocumentIds: Array.isArray(state.composeDraft.selectedDocumentIds)
                ? state.composeDraft.selectedDocumentIds
                      .map((id) => Number(id))
                      .filter((id) => !Number.isNaN(id))
                : [],
        };
    }

    function buildComposeFormData(state) {
        ensureComposeState(state);

        const { mode, emailId, recipients, subject, body, selectedDocumentIds } =
            validateComposeDraft(state);

        const formData = new FormData();
        formData.append("to", recipients.join(","));
        formData.append("body", body);

        if (mode === "new") {
            formData.append("subject", subject);
        }

        if (mode === "forward") {
            if (emailId == null || Number.isNaN(Number(emailId))) {
                throw new Error("Не удалось определить письмо для пересылки");
            }

            selectedDocumentIds.forEach((documentId) => {
                formData.append("include_document_ids", String(documentId));
            });
        }

        for (const file of state.composeDraft.files) {
            formData.append("attachments", file, file.name);
        }

        return formData;
    }

    async function submitCompose(deps) {
        const { state } = deps;
        ensureComposeState(state);

        if (state.composeDraft.isSending) return;

        try {
            const draftMeta = validateComposeDraft(state);
            const formData = buildComposeFormData(state);

            state.composeDraft.isSending = true;
            renderCompose(deps);

            if (draftMeta.mode === "forward") {
                const sender =
                    deps.sendForwardEmail ||
                    sendForwardEmail;

                if (typeof sender !== "function") {
                    throw new Error("Метод пересылки письма не подключен");
                }

                await sender(draftMeta.emailId, formData);
            } else {
                const sender =
                    deps.sendNewEmail ||
                    sendNewEmail;

                if (typeof sender !== "function") {
                    throw new Error("Метод отправки письма не подключен");
                }

                await sender(formData);
            }

            closeCompose(deps, { clear: true });
        } catch (e) {
            console.error(e);
            alert(e.message || "Не удалось отправить письмо");
            state.composeDraft.isSending = false;
            renderCompose(deps);
        }
    }

    function isComposeDirty(state) {
        ensureComposeState(state);

        return Boolean(
            String(state.composeDraft.to || "").trim() ||
                String(state.composeDraft.subject || "").trim() ||
                String(state.composeDraft.body || "").trim() ||
                (state.composeDraft.files || []).length > 0,
        );
    }

    function bindComposeEvents(deps) {
        const { state } = deps;
        ensureComposeState(state);

        const openBtn = document.getElementById("compose-open-btn");
        if (openBtn && !openBtn.dataset.composeBound) {
            openBtn.dataset.composeBound = "true";
            openBtn.addEventListener("click", () => openCompose(deps));
        }

        const overlay = document.querySelector(".compose-overlay");
        const cancelBtn = document.getElementById("compose-cancel-btn");
        const sendBtn = document.getElementById("compose-send-btn");
        const fileInput = document.getElementById("compose-file-input");

        const textInputs = [
            document.getElementById("compose-to-input"),
            document.getElementById("compose-subject-input"),
            document.getElementById("compose-body-input"),
        ].filter(Boolean);

        textInputs.forEach((input) => {
            input.addEventListener("input", (event) => handleComposeInput(event, deps));
            input.addEventListener("focus", () => {
                state.composeDraft.isFocused = true;
            });
            input.addEventListener("blur", () => {
                state.composeDraft.isFocused = false;
            });
            input.addEventListener("compositionstart", () => {
                state.composeDraft.isComposing = true;
            });
            input.addEventListener("compositionend", () => {
                state.composeDraft.isComposing = false;
            });
        });

        if (fileInput) {
            fileInput.addEventListener("click", () => {
                state.composeDraft.isFileDialogOpen = true;
            });

            fileInput.addEventListener("change", (event) => {
                state.composeDraft.isFileDialogOpen = false;
                addComposeFiles(event.target.files, deps);
            });

            fileInput.addEventListener("blur", () => {
                state.composeDraft.isFileDialogOpen = false;
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener("click", () => submitCompose(deps));
        }

        if (cancelBtn) {
            cancelBtn.addEventListener("click", () => {
                if (isComposeDirty(state)) {
                    const confirmed = window.confirm(
                        "Закрыть форму? Несохранённые данные будут потеряны.",
                    );
                    if (!confirmed) return;
                }

                closeCompose(deps, { clear: true });
            });
        }

        if (overlay) {
            overlay.addEventListener("click", (event) => {
                const closeTrigger = event.target.closest("[data-compose-close]");
                if (!closeTrigger) return;
                if (state.composeDraft.isSending) return;

                if (isComposeDirty(state)) {
                    const confirmed = window.confirm(
                        "Закрыть форму? Несохранённые данные будут потеряны.",
                    );
                    if (!confirmed) return;
                }

                closeCompose(deps, { clear: true });
            });

            overlay.addEventListener("click", (event) => {
                const removeBtn = event.target.closest("[data-compose-file-remove]");
                if (!removeBtn) return;
                if (state.composeDraft.isSending) return;

                const index = Number(removeBtn.dataset.composeFileRemove);
                if (Number.isNaN(index)) return;

                removeComposeFile(index, deps);
            });

            overlay.addEventListener("change", (event) => {
                const checkbox = event.target.closest("[data-compose-source-doc-id]");
                if (!checkbox) return;
                if (state.composeDraft.isSending) return;

                const documentId = Number(checkbox.dataset.composeSourceDocId);
                if (Number.isNaN(documentId)) return;

                toggleForwardSourceAttachment(documentId, checkbox.checked, deps);
            });
        }
    }

    function isComposeInputProtected(state) {
        ensureComposeState(state);

        return (
            state.composeDraft.isOpen === true &&
            (
                state.composeDraft.isFocused === true ||
                state.composeDraft.isComposing === true ||
                state.composeDraft.isFileDialogOpen === true ||
                state.composeDraft.isSending === true
            )
        );
    }

    function initCompose(deps) {
        const { state } = deps;
        ensureComposeState(state);
        renderCompose(deps);
    }

    window.MailCompose = {
        ensureComposeState,
        renderCompose,
        openCompose,
        openForwardCompose,
        closeCompose,
        resetComposeDraft,
        addComposeFiles,
        removeComposeFile,
        toggleForwardSourceAttachment,
        validateComposeDraft,
        buildComposeFormData,
        submitCompose,
        isComposeInputProtected,
        initCompose,
    };
})();