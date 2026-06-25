(function () {
    function initTabs(deps) {
        const { state, renderChatForEmail, renderEmailCard } = deps;

        const btns = document.querySelectorAll(".tab-button");
        const panes = document.querySelectorAll(".tab-pane");

        function switchTab(tabId) {
            btns.forEach((btn) => {
                btn.classList.remove("active");
                if (btn.dataset.tab === tabId) {
                    btn.classList.add("active");
                }
            });

            panes.forEach((pane) => {
                pane.classList.remove("active");
                if (pane.id === `tab-${tabId}`) {
                    pane.classList.add("active");
                }
            });

            if (tabId === "chat") {
                const email = state.emails.find((e) => e.id === state.selectedEmailId);
                renderChatForEmail(email);
            } else if (tabId === "emails") {
                if (state.selectedEmailId) {
                    const email = state.emails.find((e) => e.id === state.selectedEmailId);
                    if (email) {
                        renderEmailCard(email);
                        return;
                    }
                }

                const emailView = document.getElementById("emailView");
                if (emailView) {
                    emailView.innerHTML =
                        '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
                }
            }
        }

        btns.forEach((btn) => {
            btn.addEventListener("click", () => switchTab(btn.dataset.tab));
        });
    }

    async function refreshEmailsSilently(deps) {
        const {
            state,
            isChatTabActive,
            isMaterialInputProtected,
            isReplyInputProtected = () => false,
            isComposeInputProtected = () => false,
            isDecisionSelectProtected = () => false,
            loadEmailsFromApi,
            renderEmailList,
            updateUnreadCount,
            highlightSelectedEmail,
            renderChatForEmail,
            renderEmailCard,
        } = deps;

        const mySeq = state.refreshSeq;
        const prevId = state.selectedEmailId;

        const isProtectedBeforeLoad =
            isMaterialInputProtected() ||
            isReplyInputProtected(state) ||
            isComposeInputProtected(state) ||
            isDecisionSelectProtected();

        if (isProtectedBeforeLoad) {
            state.pendingSilentRefresh = true;
            return;
        }

        state.pendingSilentRefresh = false;

        await loadEmailsFromApi(false);

        if (mySeq !== state.refreshSeq) return;

        renderEmailList();
        updateUnreadCount();

        const isProtectedBeforeRender =
            isMaterialInputProtected() ||
            isReplyInputProtected(state) ||
            isComposeInputProtected(state);

        if (isProtectedBeforeRender) {
            state.pendingSilentRefresh = true;
            return;
        }

        const inChat = isChatTabActive();
        const currentEmail = prevId
            ? state.emails.find((e) => e.id === prevId)
            : null;

        if (currentEmail) {
            highlightSelectedEmail(prevId);

            if (inChat) {
                renderChatForEmail(currentEmail);
            } else {
                renderEmailCard(currentEmail);
            }
        } else if (inChat) {
            renderChatForEmail(null);
        } else {
            state.selectedEmailId = null;

            const emailView = document.getElementById("emailView");
            if (emailView) {
                emailView.innerHTML =
                    '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
            }
        }

        const submitContainer = document.querySelector(".chat-submit");
        if (submitContainer) {
            submitContainer.style.display =
                state.emails.length === 0 ? "none" : submitContainer.style.display;
        }
    }

    function initMailPage(config, deps) {
        const {
            state,
            loadEmailsFromApi,
            renderEmailList,
            updateUnreadCount,
            selectEmail,
            initTabs,
            initCompose,
            sendChatData,
        } = deps;

        const pageConfig = {
            pageType: config.pageType || "inbox",
            apiUrl: config.apiUrl || "/api/queue",
            allowCloseTask: config.allowCloseTask ?? true,
            allowDecisionEdit: config.allowDecisionEdit ?? true,
            allowChat: config.allowChat ?? true,
            refreshIntervalMs: config.refreshIntervalMs ?? 5000,
        };

        document.addEventListener("DOMContentLoaded", async () => {
            window.MAILPAGECONFIG = pageConfig;

            state.selectedEmailId = null;

            const emailView = document.getElementById("emailView");
            if (emailView) {
                emailView.innerHTML =
                    '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
            }

            await loadEmailsFromApi();
            renderEmailList();
            renderPagination();   // <-- добавить
            updateUnreadCount();
            initCompose();

            state.selectedEmailId = null;

            if (state.emails.length === 0) {
                const emailView = document.getElementById("emailView");
                if (emailView) {
                    emailView.innerHTML =
                        '<div class="email-placeholder">Письма отсутствуют</div>';
                }
            } else {
                const emailView = document.getElementById("emailView");
                if (emailView) {
                    emailView.innerHTML =
                        '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
                }
            }

            setInterval(() => {
                refreshEmailsSilently({
                    ...deps,
                    state,
                    isDecisionSelectProtected: () => isDecisionSelectFocused,
                });
            }, pageConfig.refreshIntervalMs);

            initTabs();

            const chatSendBtn = document.getElementById("chat-send-btn");
            if (chatSendBtn) {
                chatSendBtn.addEventListener("click", sendChatData);
            }

            const searchInput = document.getElementById("search-input");
            const searchClearBtn = document.getElementById("search-clear-btn");

            function updateSearchClearButton() {
                if (!searchClearBtn || !searchInput) return;
                searchClearBtn.hidden = searchInput.value.trim() === "";
            }

            if (searchInput) {
                searchInput.addEventListener("input", (e) => {
                    state.currentSearchTerm = e.target.value;
                    currentPage = 0;           // <-- добавить
                    renderEmailList();
                    updateSearchClearButton();
                });
            }

            if (searchClearBtn && searchInput) {
                searchClearBtn.addEventListener("click", () => {
                    searchInput.value = "";
                    state.currentSearchTerm = "";
                    renderEmailList();
                    updateSearchClearButton();
                    searchInput.focus();
                });
            }

            updateSearchClearButton();

            const filterToggle = document.getElementById("filter-toggle-btn");
            const filterPanel = document.getElementById("filter-panel");
            const applyBtn = document.getElementById("apply-filters-btn");
            const closeFilter = document.getElementById("close-filter-panel");
            const statusSelect = document.getElementById("status-filter-select");
            const classSelect = document.getElementById("class-filter-select");
            const sortNewestBtn = document.getElementById("sort-newest-btn");
            const sortOldestBtn = document.getElementById("sort-oldest-btn");

            function openFilterPanel() {
                if (!filterPanel) return;

                filterPanel.style.display = "block";

                if (statusSelect) statusSelect.value = state.currentStatusFilter;
                if (classSelect) classSelect.value = state.currentClassFilter;

                if (sortNewestBtn && sortOldestBtn) {
                    if (state.sortNewestFirst) {
                        sortNewestBtn.classList.add("active");
                        sortOldestBtn.classList.remove("active");
                    } else {
                        sortOldestBtn.classList.add("active");
                        sortNewestBtn.classList.remove("active");
                    }
                }
            }

            function closeFilterPanelFn() {
                if (filterPanel) filterPanel.style.display = "none";
            }

            function applyFilters() {
                if (statusSelect) state.currentStatusFilter = statusSelect.value;
                if (classSelect) state.currentClassFilter = classSelect.value;
                if (sortNewestBtn) {
                    state.sortNewestFirst = sortNewestBtn.classList.contains("active");
                }

                // Сброс пагинации и перезагрузка с сервера
                currentPage = 0;
                loadEmailsFromApi(true).then(() => {
                    renderEmailList();
                    renderPagination();   // обновить пагинацию
                    closeFilterPanelFn();
                });
            }

            if (filterToggle) {
                filterToggle.addEventListener("click", openFilterPanel);
            }

            if (applyBtn) {
                applyBtn.addEventListener("click", applyFilters);
            }

            if (closeFilter) {
                closeFilter.addEventListener("click", closeFilterPanelFn);
            }

            document.addEventListener("click", (e) => {
                if (
                    filterPanel &&
                    filterPanel.style.display === "block" &&
                    filterToggle &&
                    !filterPanel.contains(e.target) &&
                    e.target !== filterToggle &&
                    !filterToggle.contains(e.target)
                ) {
                    closeFilterPanelFn();
                }
            });

            if (sortNewestBtn && sortOldestBtn) {
                sortNewestBtn.addEventListener("click", () => {
                    sortNewestBtn.classList.add("active");
                    sortOldestBtn.classList.remove("active");
                });

                sortOldestBtn.addEventListener("click", () => {
                    sortOldestBtn.classList.add("active");
                    sortNewestBtn.classList.remove("active");
                });
            }
        });
    }

    window.MailInit = {
        initTabs,
        refreshEmailsSilently,
        initMailPage,
    };
})();