(function () {
    function showLoading() {
        const emailView = document.getElementById("emailView");
        if (emailView) {
            emailView.innerHTML =
                '<div class="email-loading-wrapper"><div class="loading"></div></div>';
        }
    }

    function highlightSelectedEmail(id) {
        document.querySelectorAll(".email-item").forEach((item) => {
            item.classList.remove("selected");
        });

        const selected = document.querySelector(`.email-item[data-id="${id}"]`);
        if (selected) {
            selected.classList.add("selected");
        }
    }

    function buildInboxHistoryState(state) {
        const pageType = window.MAILPAGECONFIG?.pageType || "inbox";

        return {
            currentPage: Math.max(1, Number(state.currentPage) || 1),
            currentSearchTerm: String(state.currentSearchTerm || ""),
            sortNewestFirst: state.sortNewestFirst !== false,
            currentStatusFilter:
                pageType !== "sent" ? String(state.currentStatusFilter || "all") : "all",
            currentClassFilter:
                pageType !== "sent" ? String(state.currentClassFilter || "all") : "all",
            selectedEmailId:
                state.selectedEmailId != null ? Number(state.selectedEmailId) : null,
            selectedSourceType: String(state.selectedSourceType || pageType),
        };
    }

    function syncInboxSelectionState(state, mode = "replace") {
        const pageType = window.MAILPAGECONFIG?.pageType || "inbox";
        const params = new URLSearchParams(window.location.search);

        if (Number(state.currentPage) > 1) {
            params.set("page", String(state.currentPage));
        } else {
            params.delete("page");
        }

        if (String(state.currentSearchTerm || "").trim()) {
            params.set("search", String(state.currentSearchTerm).trim());
        } else {
            params.delete("search");
        }

        if (state.sortNewestFirst === false) {
            params.set("sort", "oldest");
        } else {
            params.delete("sort");
        }

        if (pageType !== "sent") {
            if (state.currentStatusFilter && state.currentStatusFilter !== "all") {
                params.set("status", state.currentStatusFilter);
            } else {
                params.delete("status");
            }

            if (state.currentClassFilter && state.currentClassFilter !== "all") {
                params.set("class", state.currentClassFilter);
            } else {
                params.delete("class");
            }
        }

        if (state.selectedEmailId != null && Number(state.selectedEmailId) > 0) {
            params.set("selected_email_id", String(state.selectedEmailId));
            params.set("selected_source", String(state.selectedSourceType || pageType));
        } else {
            params.delete("selected_email_id");
            params.delete("selected_source");
        }

        const query = params.toString();
        const nextUrl = query
            ? `${window.location.pathname}?${query}`
            : window.location.pathname;

        const historyState = buildInboxHistoryState(state);

        if (mode === "push") {
            window.history.pushState(historyState, "", nextUrl);
            return;
        }

        window.history.replaceState(historyState, "", nextUrl);
    }

    function renderEmailList(deps) {
        const {
            state,
            escapeHtml,
            formatDate,
            formatTimeOnly,
            getStatusName,
            selectEmail,
        } = deps;

        const filtered = [...state.emails];

        const container = document.getElementById("emailsContainer");
        if (!container) return;

        if (filtered.length === 0) {
            container.innerHTML =
                '<div class="email-placeholder" style="padding:20px;text-align:center;">Письма отсутствуют</div>';
            return;
        }

        container.innerHTML = filtered
            .map((email) => {
                const mailParityId = Number(email.email_id || email.emailid || email.id);
                const parityClass =
                    Number.isFinite(mailParityId) && mailParityId % 2 === 0
                        ? "email-item--even"
                        : "email-item--odd";

                return `
                    <div
                        class="email-item ${email.read ? "is-read" : "is-unread"} ${parityClass}"
                        data-id="${email.id}"
                        data-email-id="${mailParityId}"
                    >
                        <div class="email-item-subject-row">
                            <div class="subject">${escapeHtml(email.subject)}</div>
                            ${email.has_comment
                                ? `
                                    <span class="email-item-comment-indicator" aria-hidden="true">
                                        <img
                                            src="/static/images/comment.svg"
                                            alt=""
                                            class="email-item-comment-indicator-icon"
                                        >
                                    </span>
                                `
                                : ""
                            }
                        </div>

                        <div class="email-item-header">
                            <div class="sender">От: ${escapeHtml(email.sender)}</div>
                            <div class="status-badge status-${escapeHtml(email.status)}">
                                ${escapeHtml(getStatusName(email.status))}
                            </div>
                        </div>
                        <div class="recipient">Кому: ${escapeHtml(email.mailbox || "")}</div>
                        <div class="date">
                            ${formatDate(email.date)}
                            <span class="email-time">${formatTimeOnly(email.date)}</span>
                        </div>
                    </div>
                `;
            })
            .join("");

        document.querySelectorAll(".email-item").forEach((el) => {
            el.addEventListener("click", async () => {
                await selectEmail(el.dataset.id, { historyMode: "push" });
            });
        });

        if (state.selectedEmailId != null) {
            highlightSelectedEmail(state.selectedEmailId);
        }
    }

    async function updateEmailReadStatus(emailId, isRead) {
        const response = await fetch(`/api/emails/${emailId}/read`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
            },
            credentials: "same-origin",
            body: JSON.stringify({ is_read: isRead }),
        });

        if (!response.ok) {
            throw new Error(`Ошибка обновления is_read: ${response.status}`);
        }

        return response.json();
    }

    function closeOpenedEmail(deps, options = {}) {
        const {
            state,
        } = deps;

        const {
            historyMode = "replace",
        } = options;

        state.selectedEmailId = null;
        state.selectedSourceType = window.MAILPAGECONFIG?.pageType || "inbox";
        state.selectedEmailSnapshot = null;
        syncInboxSelectionState(state, historyMode);

        document.querySelectorAll(".email-item").forEach((item) => {
            item.classList.remove("selected");
        });

        const emailView = document.getElementById("emailView");
        if (emailView) {
            emailView.innerHTML =
                '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
        }
    }

    async function closeAndMarkUnread(deps) {
        const {
            state,
            renderEmailList,
            updateUnreadCount,
        } = deps;

        if (!state.selectedEmailId) {
            closeOpenedEmail(deps);
            return;
        }

        const email = state.emails.find((e) => Number(e.id) === Number(state.selectedEmailId));
        if (!email) {
            closeOpenedEmail(deps);
            return;
        }

        if (!email.read) {
            closeOpenedEmail(deps);
            return;
        }

        const realEmailId = email.email_id || email.id;

        email.read = false;
        state.unreadCount += 1;

        if (typeof updateUnreadCount === "function") {
            updateUnreadCount();
        }

        if (typeof renderEmailList === "function") {
            renderEmailList();
        }

        try {
            await updateEmailReadStatus(realEmailId, false);
            closeOpenedEmail(deps);
        } catch (error) {
            console.error("Не удалось пометить письмо непрочитанным:", error);

            email.read = true;
            state.unreadCount = Math.max(0, state.unreadCount - 1);

            if (typeof updateUnreadCount === "function") {
                updateUnreadCount();
            }

            if (typeof renderEmailList === "function") {
                renderEmailList();
            }
        }
    }

    function updateUnreadCount(deps) {
        const { state, formatUnreadCount } = deps;

        const countSpan = document.getElementById("email-count-display");
        if (!countSpan) return;

        const pageType = window.MAILPAGECONFIG?.pageType || "inbox";
        if (pageType === "archived") {
            countSpan.textContent = "";
            return;
        }

        countSpan.textContent = formatUnreadCount(state.unreadCount);
    }

    async function loadInboxEmailDetail(emailId) {
        const response = await fetch(`/api/emails/${emailId}/detail`, {
            credentials: "same-origin",
        });

        if (!response.ok) {
            let detail = `Не удалось загрузить письмо (${response.status})`;

            try {
                const data = await response.json();
                if (data?.detail) {
                    detail = data.detail;
                }
            } catch (_) {}

            throw new Error(detail);
        }

        const data = await response.json();
        if (!data?.item || typeof data.item !== "object") {
            throw new Error("Некорректный ответ деталей письма");
        }

        return data.item;
    }

    async function resolveInboxEmailById(emailId, deps) {
        const {
            state,
            normalizeInboxDetailItem,
        } = deps;

        const normalizedId = Number(emailId);

        let email = state.emails.find(
            (e) =>
                Number(e.email_id || e.emailid || e.id) === normalizedId
        );
        if (email) {
            return { email, fromList: true };
        }

        const rawItem = await loadInboxEmailDetail(normalizedId);
        email =
            typeof normalizeInboxDetailItem === "function"
                ? normalizeInboxDetailItem(rawItem)
                : rawItem;

        return { email, fromList: false };
    }

    async function selectEmail(id, deps, options = {}) {
        const {
            state,
            showLoading,
            highlightSelectedEmail,
            renderEmailCard,
            renderChatForEmail,
            renderEmailList,
            updateUnreadCount,
        } = deps;

        const {
            historyMode = "push",
        } = options;

        state.selectedEmailId = parseInt(id, 10);
        state.selectedSourceType = "inbox";
        syncInboxSelectionState(state, historyMode);

        let resolved;
        try {
            resolved = await resolveInboxEmailById(state.selectedEmailId, deps);
        } catch (error) {
            console.error("Не удалось загрузить письмо", error);

            const emailView = document.getElementById("emailView");
            if (emailView) {
                emailView.innerHTML =
                    '<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки письма</div>';
            }
            return;
        }

        const { email, fromList } = resolved;
        if (!email) return;

        if (fromList) {
            state.selectedEmailSnapshot = null;
        } else {
            state.selectedEmailSnapshot = email;
        }

        const realEmailId = email.email_id || email.id;

        if (!email.read) {
            email.read = true;
            state.unreadCount = Math.max(0, state.unreadCount - 1);

            if (typeof updateUnreadCount === "function") {
                updateUnreadCount();
            }

            updateEmailReadStatus(realEmailId, true).catch((error) => {
                console.error("Не удалось отметить письмо прочитанным:", error);

                if (fromList) {
                    email.read = false;
                    state.unreadCount += 1;

                    if (typeof updateUnreadCount === "function") {
                        updateUnreadCount();
                    }

                    if (typeof renderEmailList === "function") {
                        renderEmailList();
                    }

                    if (typeof highlightSelectedEmail === "function") {
                        highlightSelectedEmail(id);
                    }
                }
            });
        }

        showLoading();

        setTimeout(async () => {
            if (fromList) {
                highlightSelectedEmail(state.selectedEmailId);
            } else {
                document.querySelectorAll(".email-item").forEach((itemEl) => {
                    itemEl.classList.remove("selected");
                });
            }

            await renderEmailCard(email);

            const chatTab = document.getElementById("tab-chat");
            if (chatTab && chatTab.classList.contains("active")) {
                renderChatForEmail(email);
            }
        }, 300);
    }

    window.MailRenderList = {
        showLoading,
        highlightSelectedEmail,
        renderEmailList,
        updateUnreadCount,
        selectEmail,
        closeOpenedEmail,
        closeAndMarkUnread,
        syncInboxSelectionState,
    };
})();