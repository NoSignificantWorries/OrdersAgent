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
            getStatusName,
            selectEmail,
        } = deps;

        let filtered = [...state.emails];

        const pageType = window.MAILPAGECONFIG?.pageType || "inbox";

        if (pageType === "archived") {
            filtered = filtered.filter((email) => email.archived === true);
        } else {
            filtered = filtered.filter((email) => email.archived !== true);
        }

        if (state.currentSearchTerm.trim() !== "") {
            const term = state.currentSearchTerm.toLowerCase();
            filtered = filtered.filter((email) =>
                email.subject.toLowerCase().includes(term) ||
                email.sender.toLowerCase().includes(term) ||
                email.mailbox.toLowerCase().includes(term) ||
                (email.content && email.content.toLowerCase().includes(term))
            );
        }

        if (state.currentStatusFilter !== "all") {
            filtered = filtered.filter((e) => {
                if (state.currentStatusFilter === "manual_review") {
                    return e.status === "materials_review" || e.status === "ml_review";
                }
                return e.status === state.currentStatusFilter;
            });
        }

        if (state.currentClassFilter !== "all") {
            filtered = filtered.filter((e) => {
                const decision = String(e.model_decision ?? "").trim().toLowerCase();
                const isUndefinedClass = decision === "" || decision === "review";

                if (state.currentClassFilter === "undefined_only") {
                    return isUndefinedClass;
                }

                return decision === state.currentClassFilter && !isUndefinedClass;
            });
        }

        filtered.sort((a, b) => {
            const dateA = new Date(a.date);
            const dateB = new Date(b.date);
            return state.sortNewestFirst ? dateB - dateA : dateA - dateB;
        });

        const container = document.getElementById("emailsContainer");
        const countSpan = document.getElementById("email-count-display");

        if (!container) return;

        if (filtered.length === 0) {
            container.innerHTML =
                '<div class="email-placeholder" style="padding:20px;text-align:center;">Письма отсутствуют</div>';
            if (countSpan) countSpan.textContent = "0";
            return;
        }

        container.innerHTML = filtered
            .map(
                (email) => `
                    <div class="email-item" data-id="${email.id}">
                        <div class="subject">${escapeHtml(email.subject)}</div>
                        <div class="email-item-header">
                            <div class="sender">${escapeHtml(email.sender)}</div>
                            <div class="status-badge status-${escapeHtml(email.status)}">
                                ${escapeHtml(getStatusName(email.status))}
                            </div>
                        </div>
                        <div class="date">${formatDate(email.date)}</div>
                    </div>
                `,
            )
            .join("");

        document.querySelectorAll(".email-item").forEach((el) => {
            el.addEventListener("click", () => selectEmail(el.dataset.id));
        });

        if (countSpan) countSpan.textContent = String(filtered.length);
    }

    function selectEmail(id, deps) {
        const {
            state,
            showLoading,
            highlightSelectedEmail,
            renderEmailCard,
            renderChatForEmail,
        } = deps;

        state.selectedEmailId = parseInt(id, 10);

        const email = state.emails.find((e) => e.id === state.selectedEmailId);
        if (!email) return;

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
        selectEmail,
    };
})();