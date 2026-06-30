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
                        <div class="subject">${escapeHtml(email.subject)}</div>
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
            el.addEventListener("click", () => selectEmail(el.dataset.id));
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

    function closeOpenedEmail(deps) {
        const { state } = deps;

        state.selectedEmailId = null;

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

        const email = state.emails.find((e) => e.id === state.selectedEmailId);
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

    function selectEmail(id, deps) {
        const {
            state,
            showLoading,
            highlightSelectedEmail,
            renderEmailCard,
            renderChatForEmail,
            renderEmailList,
            updateUnreadCount,
        } = deps;

        state.selectedEmailId = parseInt(id, 10);

        const email = state.emails.find((e) => e.id === state.selectedEmailId);
        if (!email) return;

        const realEmailId = email.email_id || email.id;

        if (!email.read) {
            email.read = true;
            state.unreadCount = Math.max(0, state.unreadCount - 1);

            if (typeof updateUnreadCount === "function") {
                updateUnreadCount();
            }

            updateEmailReadStatus(realEmailId, true).catch((error) => {
                console.error("Не удалось отметить письмо прочитанным:", error);

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
            });
        }

        showLoading();

        setTimeout(() => {
            highlightSelectedEmail(id);
            renderEmailCard(email);

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
    };
})();