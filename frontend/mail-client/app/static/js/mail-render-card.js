(function () {
    function getDisplayDocuments(email) {
        const docs = Array.isArray(email?.documents) ? email.documents : [];
        const seenNames = new Set();

        return docs.filter((doc) => {
            const documentName = String(doc?.document_name ?? "").trim();
            if (!documentName) return false;

            const key = documentName.toLowerCase();
            if (seenNames.has(key)) return false;

            seenNames.add(key);
            return true;
        });
    }

    function canCloseTask(email) {
        if (email?.archived === true) return false;

        // const status = String(
        //     email?.task_status || email?.taskstatus || email?.task?.status || email?.status || "",
        // ).toLowerCase();

        // return ["question", "error", "completed"].includes(status);

        return true;
    }

    function canUnarchiveTask(email) {
        return email?.archived === true;
    }

    function canMarkUnread() {
        return window.location.pathname === "/inbox";
    }

    function isEditingReplyInput() {
        const active = document.activeElement;
        return !!(
            active &&
            active.classList &&
            active.classList.contains("reply-body-input")
        );
    }

    function isReplyInputProtected(state) {
        const selectedId = state.selectedEmailId;

        return (
            isEditingReplyInput() ||
            state.isReplyInputFocused === true ||
            state.isReplyInputComposing === true ||
            state.isReplyFileDialogOpen === true ||
            (selectedId != null && state.openReplyForms?.has(selectedId) === true)
        );
    }

    function bindReplyInputEvents({ input, email, deps }) {
        if (!input) return;

        const { state, refreshEmailsSilently } = deps;
        const realEmailId = email.email_id || email.id;

        if (!state.replyDrafts) {
            state.replyDrafts = new Map();
        }

        if (typeof state.isReplyInputComposing === "undefined") {
            state.isReplyInputComposing = false;
        }

        input.addEventListener("focus", () => {
            state.isReplyInputFocused = true;
        });

        input.addEventListener("blur", (e) => {
            state.isReplyInputFocused = false;
            state.isReplyInputComposing = false;
            state.replyDrafts.set(realEmailId, e.target.value);

            const nextFocused = e.relatedTarget;
            const isReplyActionTarget =
                nextFocused &&
                (nextFocused.id === "reply-send-btn" ||
                nextFocused.id === "reply-cancel-btn" ||
                nextFocused.id === "reply-toggle-btn");

            if (isReplyActionTarget) {
                return;
            }

            setTimeout(() => {
                if (state.pendingSilentRefresh && !isReplyInputProtected(state)) {
                    state.pendingSilentRefresh = false;
                    refreshEmailsSilently();
                }
            }, 0);
        });

        input.addEventListener("compositionstart", () => {
            state.isReplyInputComposing = true;
        });

        input.addEventListener("compositionend", (e) => {
            state.isReplyInputComposing = false;
            state.replyDrafts.set(realEmailId, e.target.value);

            if (state.pendingSilentRefresh && !isReplyInputProtected(state)) {
                state.pendingSilentRefresh = false;
                refreshEmailsSilently();
            }
        });

        input.addEventListener("input", (e) => {
            state.replyDrafts.set(realEmailId, e.target.value);

            if (e.isComposing) {
                state.isReplyInputComposing = true;
            }
        });
    }

    const getThreadCountLabel = (count) => {
        const mod10 = count % 10;
        const mod100 = count % 100;

        if (mod10 === 1 && mod100 !== 11) return `${count} письмо`;
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
            return `${count} письма`;
        }
        return `${count} писем`;
    };

    function renderEmailCard(email, deps) {
        const {
            state,
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
        } = deps;

        const cfg = window.MAILPAGECONFIG || {};

        const formattedContent =
            (email.content || "")
                .split("\n")
                .map((line) => {
                    if (line.trim() === "") return "<br>";
                    if (line.includes("•")) {
                        return `<p style="margin-left:20px;">${escapeHtml(line)}</p>`;
                    }
                    return `<p>${escapeHtml(line)}</p>`;
                })
                .join("") || "<p>...</p>";

        const docsWithName = getDisplayDocuments(email);

        const threadMessagesRaw =
            typeof getThreadMessages === "function" ? getThreadMessages(email) : [email];

        const threadMessages = Array.isArray(threadMessagesRaw) && threadMessagesRaw.length
            ? threadMessagesRaw
            : [email];

        const hasThread = threadMessages.length > 1;
        const threadExpanded =
            hasThread && typeof isThreadExpanded === "function"
                ? isThreadExpanded(email.id)
                : false;

        const threadChevron = threadExpanded ? "▼" : "▶";

        const threadBlock = hasThread
            ? `
                <div class="email-thread-block">
                    <button
                        type="button"
                        id="thread-toggle-btn-${email.id}"
                        class="email-thread-toggle"
                        aria-expanded="${threadExpanded ? "true" : "false"}"
                        aria-controls="email-thread-panel-${email.id}"
                    >
                        <span class="email-thread-toggle-icon" aria-hidden="true">${threadChevron}</span>
                        <span class="email-thread-toggle-text">Цепочка: ${getThreadCountLabel(threadMessages.length)}</span>
                    </button>

                    <div
                        id="email-thread-panel-${email.id}"
                        class="email-thread-panel"
                        ${threadExpanded ? "" : "hidden"}
                    >
                        <div class="email-thread-timeline">
                            ${threadMessages
                                .map((threadEmail) => {
                                    const isCurrent = threadEmail.id === email.id;
                                    const previewSource =
                                        threadEmail.preview || threadEmail.content || "";
                                    const preview = escapeHtml(previewSource.slice(0, 180));

                                    return `
                                        <button
                                            type="button"
                                            class="email-thread-item ${isCurrent ? "is-current" : ""}"
                                            data-thread-email-id="${threadEmail.id}"
                                        >
                                            <span class="email-thread-marker" aria-hidden="true"></span>

                                            <span class="email-thread-item-main">
                                                <span class="email-thread-item-top">
                                                    <span class="email-thread-sender">${escapeHtml(threadEmail.sender || "Без отправителя")}</span>
                                                    ${
                                                        isCurrent
                                                            ? '<span class="email-thread-current-badge">Текущее</span>'
                                                            : ""
                                                    }
                                                </span>

                                                <span class="email-thread-item-meta">
                                                    ${formatDateTime(threadEmail.date)}
                                                </span>

                                                <span class="email-thread-item-subject">
                                                    ${escapeHtml(threadEmail.subject || "(без темы)")}
                                                </span>

                                                <span class="email-thread-item-preview">
                                                    ${preview || "Без текста"}
                                                </span>
                                            </span>
                                        </button>
                                    `;
                                })
                                .join("")}
                        </div>
                    </div>
                </div>
            `
            : "";

        const attachmentBlock = docsWithName.length
            ? `
                <div class="email-attachments">
                    <strong>Вложения:</strong>
                    <ul>
                        ${docsWithName
                            .map(
                                (doc) => `
                                    <li>${escapeHtml(doc.document_name)}</li>
                                `,
                            )
                            .join("")}
                    </ul>
                    <button class="save-all-attachments-btn" data-email-id="${email.id}">
                        Скачать
                    </button>
                </div>
            `
            : "";

        const decisionValue = email.model_decision || "";
        const decisionHtml = decisionOptions
            .map(
                (opt) => `
                    <option value="${escapeHtml(opt.value)}" ${
                        opt.value === decisionValue ? "selected" : ""
                    }>
                        ${escapeHtml(opt.label)}
                    </option>
                `,
            )
            .join("");

        const taskStatusName = getStatusName(email.status);

        const decisionBlock =
            email.task && cfg.allowDecisionEdit !== false
                ? `
                    <div class="decision-block">
                        <label for="decision-select" class="decision-label">Класс письма</label>
                        <select id="decision-select" class="decision-select">
                            ${decisionHtml}
                        </select>
                        <button id="decision-save-btn" class="decision-save-btn">Сохранить</button>
                    </div>
                `
                : "";

        const closeTaskBlock =
            cfg.allowCloseTask !== false && canCloseTask(email) && email.task?.id
                ? `
                    <div class="danger-zone">
                        <button id="close-task-btn" class="close-task-btn">
                            Закрыть задачу
                        </button>
                    </div>
                `
                : "";

        let errorIconHtml = "";
        if (email.status === "error") {
            const errorText = email.task?.error_message || "Ошибка неизвестна";
            errorIconHtml = `
                <div class="error-tooltip-container">
                    <div class="error-question-mark" data-tooltip="${escapeHtml(errorText)}">?</div>
                </div>
            `;
        }

        const unarchiveTaskBlock = canUnarchiveTask(email)
                ? `
                    <div class="danger-zone">
                        <button id="unarchive-task-btn" class="close-task-btn">
                            Вернуть во входящие
                        </button>
                    </div>
                `
                : "";

        const emailView = document.getElementById("emailView");
        if (!emailView) return;

        const realEmailId = email.email_id || email.id;
        const savedReplyDraft = state.replyDrafts?.get(realEmailId) || "";
        const shouldShowReplyForm = state.openReplyForms?.has(realEmailId) === true;

        emailView.innerHTML = `
            <div class="email-card">
                <div class="email-header">
                    <div class="email-header-top">
                        <div class="email-subject">${escapeHtml(email.subject)}</div>

                        <div class="email-header-actions">
                            <div class="status-block">
                                <div class="status-info">
                                    <span class="status-label">Состояние:</span>
                                    <div class="status-display status-${escapeHtml(email.status)}">
                                        ${escapeHtml(taskStatusName)}
                                    </div>
                                    ${errorIconHtml}
                                </div>
                            </div>

                            ${
                                canMarkUnread()
                                    ? `
                                        <div class="email-actions-menu-wrap">
                                            <button
                                                type="button"
                                                class="email-icon-btn"
                                                id="email-actions-toggle-btn"
                                                aria-label="Действия с письмом"
                                                title="Действия"
                                            >
                                                <span aria-hidden="true">⋯</span>
                                            </button>

                                            <div class="email-actions-menu" id="email-actions-menu" hidden>
                                                <button
                                                    type="button"
                                                    class="email-actions-menu-item"
                                                    id="mark-unread-btn"
                                                >
                                                    Пометить непрочитанным
                                                </button>
                                            </div>
                                        </div>
                                    `
                                    : ""
                            }

                            <button
                                type="button"
                                class="email-icon-btn"
                                id="close-email-btn"
                                aria-label="Закрыть письмо"
                                title="Закрыть"
                            >
                                <span aria-hidden="true">×</span>
                            </button>
                        </div>
                    </div>

                    <div class="email-meta">
                        <div><strong>От:</strong> ${escapeHtml(email.sender)}</div>
                        <div><strong>Кому:</strong> ${escapeHtml(email.mailbox)}</div>
                        <div><strong>Дата:</strong> ${formatDateTime(email.date)}</div>
                    </div>
                </div>

                ${threadBlock}

                <div class="email-divider"></div>

                ${attachmentBlock}
                ${decisionBlock}
                ${closeTaskBlock}
                ${unarchiveTaskBlock}

                <div class="email-body">
                    ${formattedContent}
                </div>

                <div class="reply-block">
                    <div class="reply-toolbar">
                        <button
                            type="button"
                            id="reply-toggle-btn"
                            class="reply-btn reply-btn-primary"
                            ${shouldShowReplyForm ? "hidden" : ""}
                        >
                            Ответить
                        </button>

                        <button
                            type="button"
                            id="forward-toggle-btn"
                            class="reply-btn reply-btn-secondary"
                        >
                            Переслать
                        </button>
                    </div>

                    <div
                        id="reply-form-block"
                        class="reply-form-block"
                        ${shouldShowReplyForm ? "" : "hidden"}
                    >
                        <label for="reply-body-input" class="decision-label">Текст ответа</label>
                        <textarea
                            id="reply-body-input"
                            class="reply-body-input"
                            rows="8"
                            placeholder="Введите текст ответа..."
                        ></textarea>

                        <div id="reply-files-list" class="reply-files-list"></div>

                        <div class="reply-actions">
                            <button type="button" id="reply-send-btn" class="reply-btn reply-btn-primary">
                                Отправить
                            </button>

                            <button type="button" id="reply-cancel-btn" class="reply-btn reply-btn-secondary">
                                Отмена
                            </button>

                            <input
                                id="reply-files-input"
                                class="reply-files-input-native"
                                type="file"
                                multiple
                                aria-label="Добавить вложения"
                                title="Добавить вложения"
                            />
                        </div>
                    </div>
                </div>

            </div>
        `;

        const closeEmailBtn = document.getElementById("close-email-btn");
        if (closeEmailBtn) {
            closeEmailBtn.addEventListener("click", () => {
                closeOpenedEmail();
            });
        }

        const threadToggleBtn = document.getElementById(`thread-toggle-btn-${email.id}`);
        const threadPanel = document.getElementById(`email-thread-panel-${email.id}`);

        if (threadToggleBtn && threadPanel) {
            threadToggleBtn.addEventListener("click", () => {
                if (typeof toggleThreadExpanded === "function") {
                    toggleThreadExpanded(email.id);
                }

                const expanded =
                    typeof isThreadExpanded === "function"
                        ? isThreadExpanded(email.id)
                        : false;

                threadToggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
                threadPanel.hidden = !expanded;

                const icon = threadToggleBtn.querySelector(".email-thread-toggle-icon");
                if (icon) {
                    icon.textContent = expanded ? "▼" : "▶";
                }
            });

            threadPanel.addEventListener("click", (event) => {
                const target = event.target.closest("[data-thread-email-id]");
                if (!target) return;

                event.stopPropagation();

                const targetId = Number(target.dataset.threadEmailId);
                if (Number.isNaN(targetId) || targetId === email.id) return;

                selectEmail(targetId);
            });
        }

        const replyToggleBtn = document.getElementById("reply-toggle-btn");
        const forwardToggleBtn = document.getElementById("forward-toggle-btn");
        const replyFormBlock = document.getElementById("reply-form-block");
        const replyBodyInput = document.getElementById("reply-body-input");
        const replySendBtn = document.getElementById("reply-send-btn");
        const replyCancelBtn = document.getElementById("reply-cancel-btn");
        const replyFilesInput = document.getElementById("reply-files-input");
        const replyFilesList = document.getElementById("reply-files-list");

        if (replyBodyInput) {
            replyBodyInput.value = savedReplyDraft;
            bindReplyInputEvents({
                input: replyBodyInput,
                email,
                deps,
            });
        }

        if (replyFilesInput && replyFilesList) {
            if (!state.replyFiles) {
                state.replyFiles = new Map();
            }
            if (!state.replyFiles.has(realEmailId)) {
                state.replyFiles.set(realEmailId, []);
            }

            const renderReplyFiles = () => {
                const files = state.replyFiles.get(realEmailId) || [];

                replyFilesList.innerHTML = files.length
                    ? files
                        .map(
                            (file, index) => `
                                <div class="reply-file-item">
                                    <div class="reply-file-name" title="${escapeHtml(file.name)}">
                                        ${escapeHtml(file.name)}
                                    </div>
                                    <button
                                        type="button"
                                        class="reply-file-remove-btn"
                                        data-file-index="${index}"
                                        aria-label="Убрать файл ${escapeHtml(file.name)}"
                                        title="Убрать"
                                    >
                                        ×
                                    </button>
                                </div>
                            `,
                        )
                        .join("")
                    : "";
            };

            const removeReplyFileByIndex = (removeIndex) => {
                const files = state.replyFiles.get(realEmailId) || [];
                files.splice(removeIndex, 1);
                state.replyFiles.set(realEmailId, files);
                renderReplyFiles();
                
                updateReplyFilesInput();
            };

            const updateReplyFilesInput = () => {
                const files = state.replyFiles.get(realEmailId) || [];
                const dt = new DataTransfer();
                files.forEach(file => dt.items.add(file));
                replyFilesInput.files = dt.files;
            };

            state._replyFilesHandlers = state._replyFilesHandlers || {};
            state._replyFilesHandlers[realEmailId] = {
                renderReplyFiles,
                updateReplyFilesInput,
                replyFilesInput,
                replyFilesList,
                state,
                realEmailId,
            };
            
            replyFilesInput.addEventListener("click", () => {
                state.isReplyFileDialogOpen = true;
            });

            replyFilesInput.addEventListener("change", (event) => {
                state.isReplyFileDialogOpen = false;

                const newFiles = Array.from(event.target.files || []);
                if (newFiles.length === 0) {
                    return;
                }

                const currentFiles = state.replyFiles.get(realEmailId) || [];
                
                newFiles.forEach(file => {
                    const exists = currentFiles.some(f => f.name === file.name && f.size === file.size);
                    if (!exists) {
                        currentFiles.push(file);
                    }
                });
                
                state.replyFiles.set(realEmailId, currentFiles);
                
                renderReplyFiles();
                updateReplyFilesInput();

                if (state.pendingSilentRefresh && !isReplyInputProtected(state)) {
                    state.pendingSilentRefresh = false;
                    refreshEmailsSilently();
                }
            });

            replyFilesInput.addEventListener("blur", () => {
                setTimeout(() => {
                    state.isReplyFileDialogOpen = false;

                    if (state.pendingSilentRefresh && !isReplyInputProtected(state)) {
                        state.pendingSilentRefresh = false;
                        refreshEmailsSilently();
                    }
                }, 0);
            });

            replyFilesList.addEventListener("click", (event) => {
                const removeBtn = event.target.closest(".reply-file-remove-btn");
                if (!removeBtn) {
                    return;
                }

                const removeIndex = Number(removeBtn.dataset.fileIndex);
                if (Number.isNaN(removeIndex)) {
                    return;
                }

                removeReplyFileByIndex(removeIndex);
            });

            renderReplyFiles();

            const cleanupReplyFiles = () => {
                state.replyFiles.set(realEmailId, []);
                renderReplyFiles();
                updateReplyFilesInput();
            };
        }

        if (replyToggleBtn && replyFormBlock && replyBodyInput) {
            replyToggleBtn.addEventListener("click", () => {
                state.openReplyForms?.add(realEmailId);
                replyFormBlock.hidden = false;
                replyToggleBtn.hidden = true;
                replyBodyInput.focus();
            });
        }

        if (forwardToggleBtn) {
            forwardToggleBtn.addEventListener("click", async () => {
                if (state.pendingSilentRefresh === true) {
                    state.pendingSilentRefresh = false;
                }

                forwardToggleBtn.disabled = true;

                try {
                    if (typeof window.MailPage?.openForwardCompose !== "function") {
                        throw new Error("Форма пересылки не подключена");
                    }

                    await window.MailPage.openForwardCompose({ emailId: realEmailId });
                } catch (e) {
                    console.error(e);
                    alert(e.message || "Не удалось открыть форму пересылки");
                } finally {
                    forwardToggleBtn.disabled = false;
                }
            });
        }

        if (replyCancelBtn && replyFormBlock && replyBodyInput) {
            replyCancelBtn.addEventListener("click", () => {
                replyFormBlock.hidden = true;
                if (replyToggleBtn) replyToggleBtn.hidden = false;
                replyBodyInput.value = "";
                
                const handlers = state._replyFilesHandlers?.[realEmailId];
                if (handlers) {
                    state.replyFiles.set(realEmailId, []);
                    handlers.renderReplyFiles();
                    handlers.updateReplyFilesInput();
                    handlers.replyFilesInput.value = "";
                    handlers.replyFilesList.innerHTML = "";
                } else {
                    if (replyFilesInput) {
                        state.replyFiles.set(realEmailId, []);
                        const dt = new DataTransfer();
                        replyFilesInput.files = dt.files;
                    }
                    if (replyFilesList) replyFilesList.innerHTML = "";
                }
                
                state.isReplyFileDialogOpen = false;
                state.isReplyInputFocused = false;
                state.isReplyInputComposing = false;
                state.replyDrafts.delete(realEmailId);
                state.openReplyForms?.delete(realEmailId);
            });
        }

        if (replySendBtn && replyBodyInput) {
            replySendBtn.addEventListener("click", async () => {
                const body = replyBodyInput.value.trim();
                if (!body) {
                    alert("Введите текст ответа");
                    return;
                }

                replySendBtn.disabled = true;
                if (replyToggleBtn) replyToggleBtn.disabled = true;
                if (replyCancelBtn) replyCancelBtn.disabled = true;

                try {
                    const formData = new FormData();
                    formData.append("body", body);

                    const files = state.replyFiles.get(realEmailId) || [];
                    for (const file of files) {
                        formData.append("attachments", file, file.name);
                    }
                    
                    const resp = await fetch(`/api/emails/${realEmailId}/reply`, {
                        method: "POST",
                        credentials: "same-origin",
                        body: formData,
                    });

                    if (!resp.ok) {
                        let errorMessage = "Не удалось отправить письмо";
                        try {
                            const data = await resp.json();
                            errorMessage = data.detail || errorMessage;
                        } catch (_) {}
                        throw new Error(errorMessage);
                    }

                    window.MailPage?.showMailToast?.("Письмо отправлено");
                    state.replyDrafts.delete(realEmailId);
                    state.openReplyForms?.delete(realEmailId);
                    state.isReplyInputFocused = false;
                    state.isReplyInputComposing = false;
                    replyBodyInput.value = "";

                    const handlers = state._replyFilesHandlers?.[realEmailId];
                    if (handlers) {
                        state.replyFiles.set(realEmailId, []);
                        handlers.renderReplyFiles();
                        handlers.updateReplyFilesInput();
                        handlers.replyFilesInput.value = "";
                        handlers.replyFilesList.innerHTML = "";
                    } else {
                        if (replyFilesInput) {
                            replyFilesInput.value = "";
                            state.replyFiles.set(realEmailId, []);
                            const dt = new DataTransfer();
                            replyFilesInput.files = dt.files;
                        }
                        if (replyFilesList) replyFilesList.innerHTML = "";
                    }

                    state.isReplyFileDialogOpen = false;
                    replyFormBlock.hidden = true;
                    if (replyToggleBtn) replyToggleBtn.hidden = false;
                } catch (e) {
                    console.error(e);
                    alert(e.message || "Не удалось отправить письмо");
                } finally {
                    state.isReplyFileDialogOpen = false;
                    replySendBtn.disabled = false;
                    if (replyToggleBtn) replyToggleBtn.disabled = false;
                    if (replyCancelBtn) replyCancelBtn.disabled = false;
                }
            });
        }

        const actionsToggleBtn = document.getElementById("email-actions-toggle-btn");
        const actionsMenu = document.getElementById("email-actions-menu");
        const markUnreadBtn = document.getElementById("mark-unread-btn");

        if (actionsToggleBtn && actionsMenu) {
            actionsToggleBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                actionsMenu.hidden = !actionsMenu.hidden;
            });

            document.addEventListener("click", (e) => {
                if (
                    !actionsMenu.hidden &&
                    !actionsMenu.contains(e.target) &&
                    e.target !== actionsToggleBtn &&
                    !actionsToggleBtn.contains(e.target)
                ) {
                    actionsMenu.hidden = true;
                }
            });
        }

        if (markUnreadBtn) {
            markUnreadBtn.addEventListener("click", async () => {
                markUnreadBtn.disabled = true;

                try {
                    await closeAndMarkUnread();
                } catch (e) {
                    console.error(e);
                    alert(e.message || "Не удалось пометить письмо непрочитанным");
                    markUnreadBtn.disabled = false;
                }
            });
        }

        const closeTaskBtn = document.getElementById("close-task-btn");
        if (closeTaskBtn) {
            closeTaskBtn.addEventListener("click", async () => {
                closeTaskBtn.disabled = true;

                try {
                    const realEmailId = email.email_id || email.id;

                    const resp = await fetch(`/api/emails/${realEmailId}/archive`, {
                        method: "POST",
                        credentials: "same-origin",
                    });

                    const data = await resp.json().catch(() => ({}));
                    if (!resp.ok) {
                        throw new Error(data.detail || "Не удалось архивировать письмо");
                    }

                    state.emails = state.emails.filter(
                        (item) => (item.email_id || item.id) !== realEmailId,
                    );
                    state.chatStorage.delete(email.id);
                    state.selectedEmailId = null;

                    renderEmailList();

                    state.selectedEmailId = null;

                    const emailView = document.getElementById("emailView");
                    if (emailView) {
                        emailView.innerHTML =
                            state.emails.length === 0
                                ? '<div class="email-placeholder">Письма отсутствуют</div>'
                                : '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
                    }

                } catch (e) {
                    console.error(e);
                    alert(e.message || "Ошибка архивирования");
                    closeTaskBtn.disabled = false;
                }
            });
        }

        const unarchiveTaskBtn = document.getElementById("unarchive-task-btn");
        if (unarchiveTaskBtn) {
            unarchiveTaskBtn.addEventListener("click", async () => {
                unarchiveTaskBtn.disabled = true;

                try {
                    const realEmailId = email.email_id || email.id;

                    const resp = await fetch(`/api/emails/${realEmailId}/unarchive`, {
                        method: "POST",
                        credentials: "same-origin",
                    });

                    const data = await resp.json().catch(() => ({}));
                    if (!resp.ok) {
                        throw new Error(data.detail || "Не удалось вернуть письмо во входящие");
                    }

                    state.emails = state.emails.filter(
                        (item) => (item.email_id || item.id) !== realEmailId,
                    );
                    state.chatStorage.delete(email.id);
                    state.selectedEmailId = null;

                    renderEmailList();

                    const emailView = document.getElementById("emailView");
                    if (emailView) {
                        emailView.innerHTML =
                            state.emails.length === 0
                                ? '<div class="email-placeholder">Письма отсутствуют</div>'
                                : '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
                    }
                } catch (e) {
                    console.error(e);
                    alert(e.message || "Ошибка возврата письма");
                    unarchiveTaskBtn.disabled = false;
                }
            });
        }

        const saveBtn = document.getElementById("decision-save-btn");
        const sel = document.getElementById("decision-select");

        if (sel) {
            sel.addEventListener("focus", () => {
                state.isDecisionSelectFocused = true;
            });

            sel.addEventListener("blur", () => {
                setTimeout(() => {
                    state.isDecisionSelectFocused = false;
                }, 200);
            });

            sel.addEventListener("change", () => {
                state.isDecisionSelectFocused = true;
            });
        }

        if (saveBtn && sel && email.task?.id) {
            saveBtn.onclick = async () => {
                const newVal = sel.value || null;

                if (
                    newVal !== "request" &&
                    newVal !== "calculation" &&
                    newVal !== "question"
                ) {
                    alert(
                        "Выберите итоговый класс: «Заявка», «Расчёт» или «Вопрос».",
                    );
                    return;
                }

                const nextStatus =
                    newVal === "question" ? "question" : "ml_classified";

                try {
                    const resp = await fetch(
                        `/api/queue/${email.task.id}/decision`,
                        {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            credentials: "same-origin",
                            body: JSON.stringify({
                                model_decision: newVal,
                                status: nextStatus,
                            }),
                        },
                    );

                    const data = await resp.json().catch(() => ({}));
                    if (!resp.ok) {
                        throw new Error(data.detail || "Ошибка сохранения");
                    }

                    const task = data.task || {};
                    const output = task.output_data || {};

                    email.model_decision =
                        output.model_decision ||
                        email.model_decision ||
                        newVal ||
                        "";
                    email.predicted_class =
                        output.predicted_class ?? email.predicted_class;
                    email.prob_1 = output.prob_1 ?? email.prob_1;

                    if (email.task) {
                        email.task.status = task.status || email.task.status;
                        email.task.assigned_to =
                            task.assigned_to ?? email.task.assigned_to;
                        email.task.output_data = output;
                        email.task.completed_at =
                            task.completed_at || email.task.completed_at;

                        email.taskstatus = email.task.status;
                        email.task_status = email.task.status;
                        email.status = mapTaskStatusToUiStatus(email.task.status);
                    }

                    email.read = false;
            
                    state.unreadCount = (state.unreadCount || 0) + 1;
                    if (typeof updateUnreadCount === 'function') {
                        updateUnreadCount();
                    }

                    try {
                        const realEmailId = email.email_id || email.id;
                        await fetch(`/api/emails/${realEmailId}/read`, {
                            method: "PATCH",
                            headers: {
                                "Content-Type": "application/json",
                            },
                            credentials: "same-origin",
                            body: JSON.stringify({ is_read: false }),
                        });
                    } catch (markError) {
                        console.error("Не удалось пометить письмо непрочитанным:", markError);
                    }

                    renderEmailList();
                    highlightSelectedEmail(email.id);
                    renderEmailCard(email, deps);

                    if (typeof closeOpenedEmail === 'function') {
                        closeOpenedEmail();
                    }


                } catch (e) {
                    console.error(e);
                    alert(e.message || "Ошибка");
                }
            };
        }

        const saveAttachmentsBtn = document.querySelector(
            ".save-all-attachments-btn",
        );
        if (saveAttachmentsBtn) {
            saveAttachmentsBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await downloadEmailAttachments(email, getDisplayDocuments);
            });
        }
    }

    window.MailRenderCard = {
        getDisplayDocuments,
        canCloseTask,
        renderEmailCard,
        canUnarchiveTask,
        isEditingReplyInput,
        isReplyInputProtected,
        bindReplyInputEvents,
    };
})();