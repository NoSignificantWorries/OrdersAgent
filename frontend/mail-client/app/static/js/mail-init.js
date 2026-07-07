(function () {
    function readListStateFromUrl(pageType) {
        const params = new URLSearchParams(window.location.search);

        const page = Math.max(1, Number(params.get("page")) || 1);
        const search = params.get("search") || "";
        const sort = params.get("sort") === "oldest" ? "oldest" : "newest";

        return {
            page,
            perPage: 100,
            search,
            sortNewestFirst: sort !== "oldest",
            status: pageType === "sent" ? "all" : (params.get("status") || "all"),
            classFilter: pageType === "sent" ? "all" : (params.get("class") || "all"),
        };
    }

    function writeListStateToUrl(pageType, state) {
        const params = new URLSearchParams();

        if (Number(state.currentPage) > 1) {
            params.set("page", String(state.currentPage));
        }

        if (String(state.currentSearchTerm || "").trim()) {
            params.set("search", String(state.currentSearchTerm).trim());
        }

        if (state.sortNewestFirst === false) {
            params.set("sort", "oldest");
        }

        if (pageType !== "sent") {
            if (state.currentStatusFilter && state.currentStatusFilter !== "all") {
                params.set("status", state.currentStatusFilter);
            }

            if (state.currentClassFilter && state.currentClassFilter !== "all") {
                params.set("class", state.currentClassFilter);
            }
        }

        const query = params.toString();
        const nextUrl = query
            ? `${window.location.pathname}?${query}`
            : window.location.pathname;

        window.history.replaceState({}, "", nextUrl);
    }

    function updateSectionNavLinks(state) {
        const navLinks = document.querySelectorAll(".header-nav a.nav-btn");
        if (!navLinks.length) return;

        navLinks.forEach((link) => {
            const rawHref = link.getAttribute("href");
            if (!rawHref) return;

            try {
                const url = new URL(rawHref, window.location.origin);
                const params = new URLSearchParams();

                if (String(state.currentSearchTerm || "").trim()) {
                    params.set("search", String(state.currentSearchTerm).trim());
                }

                if (state.sortNewestFirst === false) {
                    params.set("sort", "oldest");
                }

                const isSentLink = url.pathname === "/sent";

                if (!isSentLink) {
                    if (state.currentStatusFilter && state.currentStatusFilter !== "all") {
                        params.set("status", state.currentStatusFilter);
                    }

                    if (state.currentClassFilter && state.currentClassFilter !== "all") {
                        params.set("class", state.currentClassFilter);
                    }
                }

                link.href = params.toString()
                    ? `${url.pathname}?${params.toString()}`
                    : url.pathname;
            } catch (error) {
                console.error("Не удалось обновить ссылку раздела", error);
            }
        });
    }

    function syncListState(pageType, state) {
        writeListStateToUrl(pageType, state);
        updateSectionNavLinks(state);
    }

    function initTabs(deps) {
        const { state, renderChatForEmail, renderEmailCard } = deps;

        const btns = document.querySelectorAll(".tab-button");
        const panes = document.querySelectorAll(".tab-pane");

        async function switchTab(tabId) {
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
                        await renderEmailCard(email);
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
            btn.addEventListener("click", async () => {
                await switchTab(btn.dataset.tab);
            });
        });
    }

    function buildVisiblePages(currentPage, totalPages, maxVisible = 7) {
        if (totalPages <= maxVisible) {
            return Array.from({ length: totalPages }, (_, i) => i + 1);
        }

        const pages = [1];
        const start = Math.max(2, currentPage - 1);
        const end = Math.min(totalPages - 1, currentPage + 1);

        if (start > 2) pages.push("...");

        for (let i = start; i <= end; i += 1) {
            pages.push(i);
        }

        if (end < totalPages - 1) pages.push("...");

        pages.push(totalPages);
        return pages;
    }

    function renderPagination(deps) {
        const { state, reloadEmails } = deps;

        const root = document.getElementById("emails-pagination");
        const pagesEl = document.getElementById("pagination-pages");
        const prevBtn = document.getElementById("pagination-prev-btn");
        const nextBtn = document.getElementById("pagination-next-btn");

        if (!root || !pagesEl || !prevBtn || !nextBtn) return;

        if (!state.totalPages || state.totalPages <= 1) {
            root.hidden = true;
            pagesEl.innerHTML = "";
            prevBtn.disabled = true;
            nextBtn.disabled = true;
            return;
        }

        root.hidden = false;
        pagesEl.innerHTML = "";

        const pages = buildVisiblePages(state.currentPage, state.totalPages, 7);

        pages.forEach((page) => {
            if (page === "...") {
                const dots = document.createElement("span");
                dots.className = "pagination-dots";
                dots.textContent = "…";
                pagesEl.appendChild(dots);
                return;
            }

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "pagination-page-btn";
            btn.textContent = String(page);
            btn.setAttribute("aria-label", `Страница ${page}`);

            if (page === state.currentPage) {
                btn.classList.add("active");
                btn.setAttribute("aria-current", "page");
            }

            btn.addEventListener("click", async () => {
                if (page === state.currentPage) return;

                state.currentPage = page;
                state.selectedEmailId = null;
                syncListState(window.MAILPAGECONFIG?.pageType || "inbox", state);

                await reloadEmails({ showLoadingState: true });

                const emailView = document.getElementById("emailView");
                if (emailView) {
                    emailView.innerHTML =
                        '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
                }
            });

            pagesEl.appendChild(btn);
        });

        prevBtn.disabled = state.currentPage <= 1;
        nextBtn.disabled = state.currentPage >= state.totalPages;

        prevBtn.onclick = async () => {
            if (state.currentPage <= 1) return;
            state.currentPage -= 1;
            state.selectedEmailId = null;
            syncListState(window.MAILPAGECONFIG?.pageType || "inbox", state);
            await reloadEmails({ showLoadingState: true });
        };

        nextBtn.onclick = async () => {
            if (state.currentPage >= state.totalPages) return;
            state.currentPage += 1;
            state.selectedEmailId = null;
            syncListState(window.MAILPAGECONFIG?.pageType || "inbox", state);
            await reloadEmails({ showLoadingState: true });
        };
    }

    async function refreshEmailsSilently(deps) {
        const {
            state,
            archived = null,
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

        const result = await loadEmailsFromApi({
            showLoadingState: false,
            normalizeApiItem: deps.normalizeApiItem,
            page: state.currentPage,
            perPage: state.perPage,
            extraParams: {
                search: state.currentSearchTerm,
                status: state.currentStatusFilter,
                class: state.currentClassFilter,
                sort: state.sortNewestFirst ? "newest" : "oldest",
                archived,
            },
        });

        if (mySeq !== state.refreshSeq) return;
        if (!result.ok) return;

        state.emails = result.emails;
        state.currentPage = result.pagination.page;
        state.perPage = result.pagination.perPage;
        state.totalEmails = result.pagination.total;
        state.totalPages = result.pagination.totalPages;
        state.unreadCount = state.emails.filter((email) => !email.read).length;

        renderEmailList();
        updateUnreadCount();

        if (typeof deps.renderPagination === "function") {
            deps.renderPagination();
        }

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
                await renderEmailCard(currentEmail);
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

        const reloadEmails = async ({ showLoadingState = true } = {}) => {
            const result = await loadEmailsFromApi({
                showLoadingState,
                normalizeApiItem: deps.normalizeApiItem,
                page: state.currentPage,
                perPage: state.perPage,
                extraParams: {
                    search: state.currentSearchTerm,
                    status: state.currentStatusFilter,
                    class: state.currentClassFilter,
                    sort: state.sortNewestFirst ? "newest" : "oldest",
                    archived: pageConfig.archived,
                },
            });

            if (!result.ok) return result;

            state.emails = result.emails;
            state.currentPage = result.pagination.page;
            state.perPage = result.pagination.perPage;
            state.totalEmails = result.pagination.total;
            state.totalPages = result.pagination.totalPages;
            state.unreadCount = state.emails.filter((email) => !email.read).length;

            renderEmailList();
            updateUnreadCount();
            renderPagination({ state, reloadEmails });
            syncListState(pageConfig.pageType, state);

            return result;
        };

        const pageConfig = {
            pageType: config.pageType || "inbox",
            apiUrl: config.apiUrl || "/api/queue",
            archived: typeof config.archived === "boolean" ? config.archived : null,
            allowCloseTask: config.allowCloseTask ?? true,
            allowDecisionEdit: config.allowDecisionEdit ?? true,
            allowChat: config.allowChat ?? true,
            refreshIntervalMs: config.refreshIntervalMs ?? 5000,
        };

        document.addEventListener("DOMContentLoaded", async () => {
            window.MAILPAGECONFIG = pageConfig;

            const initialUrlState = readListStateFromUrl(pageConfig.pageType);

            state.selectedEmailId = null;
            state.currentPage = initialUrlState.page;
            state.perPage = initialUrlState.perPage;
            state.totalEmails = 0;
            state.totalPages = 1;
            state.currentSearchTerm = initialUrlState.search;
            state.currentStatusFilter = initialUrlState.status;
            state.currentClassFilter = initialUrlState.classFilter;
            state.sortNewestFirst = initialUrlState.sortNewestFirst;

            const emailView = document.getElementById("emailView");
            if (emailView) {
                emailView.innerHTML =
                    '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
            }

            await reloadEmails({ showLoadingState: true });
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
                    archived: pageConfig.archived,
                    renderPagination: () => renderPagination({ state, reloadEmails }),
                    isDecisionSelectProtected: () => state.isDecisionSelectFocused === true,
                });
            }, pageConfig.refreshIntervalMs);

            initTabs({
                ...deps,
                state,
            });

            const chatSendBtn = document.getElementById("chat-send-btn");
            if (chatSendBtn) {
                chatSendBtn.addEventListener("click", sendChatData);
            }

            const searchInput = document.getElementById("search-input");
            const searchClearBtn = document.getElementById("search-clear-btn");

            if (searchInput) {
                searchInput.value = state.currentSearchTerm || "";
            }

            function updateSearchClearButton() {
                if (!searchClearBtn || !searchInput) return;
                searchClearBtn.hidden = searchInput.value.trim() === "";
            }

            if (searchInput) {
                let searchDebounceTimer = null;

                searchInput.addEventListener("input", (e) => {
                    state.currentSearchTerm = e.target.value;
                    state.currentPage = 1;
                    updateSearchClearButton();
                    syncListState(pageConfig.pageType, state);

                    clearTimeout(searchDebounceTimer);
                    searchDebounceTimer = setTimeout(() => {
                        reloadEmails({ showLoadingState: false });
                    }, 300);
                });
            }

            if (searchClearBtn && searchInput) {
                searchClearBtn.addEventListener("click", () => {
                    searchInput.value = "";
                    state.currentSearchTerm = "";
                    state.currentPage = 1;
                    updateSearchClearButton();
                    syncListState(pageConfig.pageType, state);
                    reloadEmails({ showLoadingState: true });
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

            if (statusSelect) {
                statusSelect.value = state.currentStatusFilter || "all";
            }

            if (classSelect) {
                classSelect.value = state.currentClassFilter || "all";
            }

            if (sortNewestBtn && sortOldestBtn) {
                if (state.sortNewestFirst) {
                    sortNewestBtn.classList.add("active");
                    sortOldestBtn.classList.remove("active");
                } else {
                    sortOldestBtn.classList.add("active");
                    sortNewestBtn.classList.remove("active");
                }
            }

            syncListState(pageConfig.pageType, state);

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

                state.currentPage = 1;
                syncListState(pageConfig.pageType, state);
                closeFilterPanelFn();
                reloadEmails({ showLoadingState: true });
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