(function () {
    const {
        getEmailComment,
        updateEmailComment,
    } = window.MailApi || {};

    let modalOpen = false;
    let modalSaving = false;
    let modalMode = "edit";
    let currentEmail = null;
    let currentDeps = null;
    let draftComment = "";

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function getRoot() {
        let root = document.getElementById("comment-modal-root");
        if (!root) {
            root = document.createElement("div");
            root.id = "comment-modal-root";
            document.body.appendChild(root);
        }
        return root;
    }

    function syncProtectedState() {
        if (currentDeps?.state) {
            currentDeps.state.isCommentModalOpen = modalOpen;
            currentDeps.state.isCommentModalSaving = modalSaving;
        }
    }

    function closeModal() {
        modalOpen = false;
        modalSaving = false;
        modalMode = "edit";
        currentEmail = null;
        currentDeps = null;
        draftComment = "";
        syncProtectedState();
        renderModal();
    }

    function renderModal() {
        const root = getRoot();

        if (!modalOpen || !currentEmail) {
            root.innerHTML = "";
            return;
        }

        const title =
            modalMode === "view"
                ? "Комментарий"
                : ((currentEmail.has_comment === true || String(currentEmail.comment_text || "").trim())
                    ? "Изменить комментарий"
                    : "Добавить комментарий");

        const bodyHtml =
            modalMode === "view"
                ? `
                    <div class="comment-modal-body">
                        <div class="comment-modal-text-readonly">
                            <div class="comment-modal-text-content">
                                ${String(draftComment || "").trim()
                                    ? escapeHtml(draftComment).replace(/\n/g, "<br>")
                                    : "Комментарий отсутствует"}
                            </div>
                        </div>
                    </div>
                `
                : `
                    <div class="comment-modal-body">
                        <label for="comment-modal-textarea" class="comment-modal-label">
                            Текст комментария
                        </label>
                        <textarea
                            id="comment-modal-textarea"
                            class="comment-modal-textarea"
                            rows="6"
                            placeholder="Введите комментарий"
                            ${modalSaving ? "disabled" : ""}
                        >${escapeHtml(draftComment)}</textarea>
                    </div>
                `;

        const footerHtml =
            modalMode === "view"
                ? `
                    <div class="comment-modal-footer">
                        <button
                            type="button"
                            id="comment-modal-close-btn"
                            class="comment-modal-primary-btn"
                        >
                            Закрыть
                        </button>
                    </div>
                `
                : `
                    <div class="comment-modal-footer">
                        <button
                            type="button"
                            id="comment-modal-cancel-btn"
                            class="comment-modal-secondary-btn"
                            ${modalSaving ? "disabled" : ""}
                        >
                            Отмена
                        </button>
                        <button
                            type="button"
                            id="comment-modal-save-btn"
                            class="comment-modal-primary-btn"
                            ${modalSaving ? "disabled" : ""}
                        >
                            ${modalSaving ? "Сохранение..." : "Сохранить"}
                        </button>
                    </div>
                `;

        root.innerHTML = `
            <div class="comment-modal-overlay is-open">
                <div class="comment-modal-backdrop" data-comment-close="backdrop"></div>
                <div
                    class="comment-modal"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="comment-modal-title"
                >
                    <div class="comment-modal-header">
                        <h2 id="comment-modal-title" class="comment-modal-title">${escapeHtml(title)}</h2>
                        <button
                            type="button"
                            class="comment-modal-close-btn"
                            data-comment-close="button"
                            aria-label="Закрыть окно"
                            title="Закрыть"
                            ${modalSaving ? "disabled" : ""}
                        >
                            ×
                        </button>
                    </div>

                    ${bodyHtml}
                    ${footerHtml}
                </div>
            </div>
        `;

        bindModalEvents();

        if (modalMode === "edit" && !modalSaving) {
            const textarea = document.getElementById("comment-modal-textarea");
            if (textarea) {
                textarea.focus();
                textarea.setSelectionRange(textarea.value.length, textarea.value.length);
            }
        }
    }

    function applyCommentToEmail(commentText) {
        if (!currentEmail) return;

        const normalized = String(commentText || "").trim();
        currentEmail.comment_text = normalized || null;
        currentEmail.has_comment = Boolean(normalized);

        if (currentDeps?.state?.emails && Array.isArray(currentDeps.state.emails)) {
            const realEmailId = Number(currentEmail.email_id || currentEmail.id || 0);
            const target = currentDeps.state.emails.find(
                (item) => Number(item.email_id || item.id || 0) === realEmailId
            );

            if (target) {
                target.comment_text = normalized || null;
                target.has_comment = Boolean(normalized);
            }
        }
    }

    async function saveComment() {
        if (!currentEmail || !currentDeps) return;
        if (typeof updateEmailComment !== "function") {
            throw new Error("API комментариев не подключен");
        }

        const emailRef = currentEmail;
        const depsRef = currentDeps;

        const textarea = document.getElementById("comment-modal-textarea");
        draftComment = textarea ? textarea.value : draftComment;

        modalSaving = true;
        syncProtectedState();
        renderModal();

        try {
            const realEmailId = Number(emailRef.email_id || emailRef.id || 0);
            const result = await updateEmailComment(realEmailId, draftComment);

            const savedCommentText = String(result?.comment_text || "").trim();

            currentEmail = emailRef;
            currentDeps = depsRef;
            applyCommentToEmail(savedCommentText);

            if (typeof depsRef.renderEmailList === "function") {
                depsRef.renderEmailList();
            }

            if (typeof depsRef.renderEmailCard === "function") {
                await depsRef.renderEmailCard(emailRef);
            }

            window.MailPage?.showMailToast?.(
                savedCommentText ? "Комментарий сохранен" : "Комментарий удален"
            );

            closeModal();
        } catch (error) {
            console.error(error);
            modalSaving = false;
            currentEmail = emailRef;
            currentDeps = depsRef;
            syncProtectedState();
            renderModal();
            alert(error.message || "Не удалось сохранить комментарий");
        }
    }

    function bindModalEvents() {
        const overlay = document.querySelector(".comment-modal-overlay");
        const textarea = document.getElementById("comment-modal-textarea");
        const saveBtn = document.getElementById("comment-modal-save-btn");
        const cancelBtn = document.getElementById("comment-modal-cancel-btn");
        const closeBtn = document.getElementById("comment-modal-close-btn");

        if (textarea) {
            textarea.addEventListener("input", (event) => {
                draftComment = event.target.value;
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener("click", async () => {
                if (modalSaving) return;
                await saveComment();
            });
        }

        if (cancelBtn) {
            cancelBtn.addEventListener("click", () => {
                if (modalSaving) return;
                closeModal();
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                if (modalSaving) return;
                closeModal();
            });
        }

        if (overlay) {
            overlay.addEventListener("click", (event) => {
                const closeTrigger = event.target.closest("[data-comment-close]");
                if (!closeTrigger) return;
                if (modalSaving) return;
                closeModal();
            });
        }
    }

    async function openCommentEditor(email, deps) {
        if (!email) {
            throw new Error("Письмо не передано");
        }
        if (typeof getEmailComment !== "function") {
            throw new Error("API комментариев не подключен");
        }

        currentEmail = email;
        currentDeps = deps || null;
        modalMode = "edit";
        modalSaving = false;
        modalOpen = true;
        syncProtectedState();

        try {
            const realEmailId = Number(email.email_id || email.id || 0);
            const data = await getEmailComment(realEmailId);
            draftComment = String(data?.comment_text || "");
            renderModal();
        } catch (error) {
            modalOpen = false;
            syncProtectedState();
            renderModal();
            throw error;
        }
    }

    async function openCommentViewer(email, deps) {
        if (!email) {
            throw new Error("Письмо не передано");
        }
        if (typeof getEmailComment !== "function") {
            throw new Error("API комментариев не подключен");
        }

        currentEmail = email;
        currentDeps = deps || null;
        modalMode = "view";
        modalSaving = false;
        modalOpen = true;
        syncProtectedState();

        try {
            const realEmailId = Number(email.email_id || email.id || 0);
            const data = await getEmailComment(realEmailId);
            draftComment = String(data?.comment_text || "");
            renderModal();
        } catch (error) {
            modalOpen = false;
            syncProtectedState();
            renderModal();
            throw error;
        }
    }

    function handleEscape(event) {
        if (event.key !== "Escape") return;
        if (!modalOpen) return;
        if (modalSaving) return;
        closeModal();
    }

    if (!document.body.dataset.commentEscapeBound) {
        document.body.dataset.commentEscapeBound = "true";
        document.addEventListener("keydown", handleEscape);
    }

    window.MailComments = {
        openCommentEditor,
        openCommentViewer,
        closeModal,
    };
})();