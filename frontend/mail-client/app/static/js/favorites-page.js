(function () {
    const PAGE_LIMIT = 50;
    const SEARCH_DELAY_MS = 350;

    const api = window.FavoritesApi;
    const { escapeHtml, escapeAttr } = window.MailFormatters;

    const state = {
        items: [],
        nextCursor: null,
        hasMore: false,
        search: "",

        loading: false,
        loadingMore: false,
        saving: false,

        editorOpen: false,
        editingId: null,
        draft: {
            email: "",
            comment: "",
        },

        error: "",
        retryMode: null,
        notice: "",

        controller: null,
        requestSequence: 0,
        searchTimer: null,
    };

    function getElements() {
        return {
            addButton: document.getElementById("favorites-add-btn"),
            searchInput: document.getElementById("favorites-search-input"),
            searchClear: document.getElementById("favorites-search-clear-btn"),
            status: document.getElementById("favorites-status"),
            error: document.getElementById("favorites-error"),
            errorText: document.getElementById("favorites-error-text"),
            retryButton: document.getElementById("favorites-retry-btn"),
            tableBody: document.getElementById("favorites-table-body"),
            emptyState: document.getElementById("favorites-empty-state"),
            loadMoreButton: document.getElementById("favorites-load-more-btn"),
        };
    }

    function isBusy() {
        return state.loading || state.loadingMore || state.saving;
    }

    function clearError() {
        state.error = "";
        state.retryMode = null;
    }

    function renderEditor() {
        const disabled = state.saving ? "disabled" : "";

        return `
            <tr class="materials-row is-editing">
                <td>
                    <input
                        type="email"
                        class="materials-input"
                        data-favorite-field="email"
                        value="${escapeAttr(state.draft.email)}"
                        maxlength="255"
                        placeholder="client@example.com"
                        aria-label="Почтовый адрес"
                        autocomplete="off"
                        required
                        ${disabled}
                    >
                    <div class="favorites-field-hint">
                        Один адрес без имени отправителя
                    </div>
                </td>

                <td>
                    <textarea
                        class="materials-input favorites-comment-input"
                        data-favorite-field="comment"
                        placeholder="Необязательный комментарий"
                        aria-label="Комментарий"
                        ${disabled}
                    >${escapeHtml(state.draft.comment)}</textarea>
                </td>

                <td class="materials-actions-cell">
                    <div class="materials-actions">
                        <button
                            type="button"
                            class="materials-save-btn"
                            data-favorite-action="save"
                            ${disabled}
                        >
                            ${state.saving ? "Сохранение..." : "Сохранить"}
                        </button>

                        <button
                            type="button"
                            class="materials-cancel-btn"
                            data-favorite-action="cancel"
                            ${disabled}
                        >
                            Отмена
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    function renderRow(item) {
        if (state.editorOpen && state.editingId === item.id) {
            return renderEditor();
        }

        const disabled = isBusy() || state.editorOpen ? "disabled" : "";

        return `
            <tr class="materials-row">
                <td class="favorites-email-cell">
                    ${escapeHtml(item.email)}
                </td>

                <td class="favorites-comment-cell">${item.comment
                    ? escapeHtml(item.comment)
                    : '<span class="favorites-empty-comment">Не указан</span>'
                }</td>

                <td class="materials-actions-cell">
                    <div class="materials-actions">
                        <button
                            type="button"
                            class="favorites-edit-btn"
                            data-favorite-action="edit"
                            data-favorite-id="${escapeAttr(item.id)}"
                            aria-label="Изменить ${escapeAttr(item.email)}"
                            ${disabled}
                        >
                            Изменить
                        </button>

                        <button
                            type="button"
                            class="favorites-delete-btn"
                            data-favorite-action="delete"
                            data-favorite-id="${escapeAttr(item.id)}"
                            aria-label="Удалить ${escapeAttr(item.email)}"
                            ${disabled}
                        >
                            Удалить
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    function render() {
        const elements = getElements();
        const busy = isBusy();

        elements.addButton.disabled = busy || state.editorOpen;

        const searchLocked = state.saving || state.editorOpen;

        elements.searchInput.disabled = searchLocked;
        elements.searchClear.disabled = searchLocked;
        elements.searchClear.hidden =
            elements.searchInput.value.trim() === "";

        elements.error.hidden = !state.error;
        elements.errorText.textContent = state.error;
        elements.retryButton.hidden = !state.retryMode;
        elements.retryButton.disabled = busy || state.editorOpen;

        let statusText = state.notice;

        if (state.loading) {
            statusText = "Загрузка избранных почт...";
        } else if (state.loadingMore) {
            statusText = "Загрузка следующей части списка...";
        } else if (state.saving) {
            statusText = "Сохранение изменений...";
        }

        elements.status.textContent = statusText;
        elements.status.hidden = !statusText;

        if (state.loading && state.items.length === 0) {
            elements.tableBody.innerHTML = `
                <tr>
                    <td colspan="3" class="materials-loading-cell">
                        Загрузка избранных почт...
                    </td>
                </tr>
            `;
        } else {
            const createRow =
                state.editorOpen && state.editingId === null
                    ? renderEditor()
                    : "";

            elements.tableBody.innerHTML =
                createRow + state.items.map(renderRow).join("");
        }

        const showEmpty =
            !state.loading &&
            !state.error &&
            !state.editorOpen &&
            state.items.length === 0;

        elements.emptyState.hidden = !showEmpty;
        elements.emptyState.textContent = showEmpty
            ? (
                state.search
                    ? "По вашему запросу ничего не найдено."
                    : "Избранных адресов пока нет. Нажмите «Добавить почту»."
            )
            : "";

        elements.loadMoreButton.hidden =
            !state.hasMore || state.loading || state.items.length === 0;

        elements.loadMoreButton.disabled = busy || state.editorOpen;
        elements.loadMoreButton.textContent =
            state.loadingMore ? "Загрузка..." : "Показать ещё";
    }

    function clearSearchTimer() {
        if (state.searchTimer !== null) {
            clearTimeout(state.searchTimer);
            state.searchTimer = null;
        }
    }

    function invalidateRequest() {
        state.requestSequence += 1;

        if (state.controller) {
            state.controller.abort();
            state.controller = null;
        }
    }

    async function loadPage(append = false) {
        if (state.editorOpen || state.saving) return;

        if (
            append &&
            (state.loading || state.loadingMore || !state.hasMore)
        ) {
            return;
        }

        clearSearchTimer();
        invalidateRequest();

        const sequence = state.requestSequence;
        const controller = new AbortController();
        state.controller = controller;

        clearError();

        if (append) {
            state.loadingMore = true;
        } else {
            state.loading = true;
            state.loadingMore = false;
            state.items = [];
            state.nextCursor = null;
            state.hasMore = false;
        }

        render();

        try {
            const result = await api.loadFavoriteSenders({
                cursor: append ? state.nextCursor : null,
                limit: PAGE_LIMIT,
                search: state.search,
                signal: controller.signal,
            });

            if (sequence !== state.requestSequence) return;

            const nextItems = Array.isArray(result.items)
                ? result.items
                : [];

            if (append) {
                const existingIds = new Set(
                    state.items.map((item) => item.id),
                );

                state.items = [
                    ...state.items,
                    ...nextItems.filter((item) => !existingIds.has(item.id)),
                ];
            } else {
                state.items = nextItems;
            }

            state.nextCursor = result.next_cursor ?? null;
            state.hasMore = result.has_more === true;
        } catch (error) {
            if (
                sequence !== state.requestSequence ||
                error?.name === "AbortError"
            ) {
                return;
            }

            console.error("Ошибка загрузки избранных", error);
            state.error = error.message || "Не удалось загрузить список";
            state.retryMode = append ? "more" : "first";
        } finally {
            if (sequence === state.requestSequence) {
                state.loading = false;
                state.loadingMore = false;
                state.controller = null;
                render();
            }
        }
    }

    function focusEmailInput() {
        const input = document.querySelector(
            '[data-favorite-field="email"]',
        );

        input?.focus();
    }

    function beginCreate() {
        if (isBusy() || state.editorOpen) return;

        clearSearchTimer();
        clearError();
        state.notice = "";

        state.editorOpen = true;
        state.editingId = null;
        state.draft = { email: "", comment: "" };

        render();
        focusEmailInput();
    }

    function beginEdit(senderId) {
        if (isBusy() || state.editorOpen) return;

        const item = state.items.find((entry) => entry.id === senderId);
        if (!item) return;

        clearSearchTimer();
        clearError();
        state.notice = "";

        state.editorOpen = true;
        state.editingId = item.id;
        state.draft = {
            email: item.email || "",
            comment: item.comment || "",
        };

        render();
        focusEmailInput();
    }

    function resetEditor() {
        state.editorOpen = false;
        state.editingId = null;
        state.draft = { email: "", comment: "" };
    }

    function cancelEditor() {
        if (state.saving) return;

        resetEditor();
        clearError();
        render();
    }

    async function saveEditor() {
        if (!state.editorOpen || isBusy()) return;

        const input = document.querySelector(
            '[data-favorite-field="email"]',
        );

        if (!input) return;

        input.value = state.draft.email.trim();
        state.draft.email = input.value;

        if (!input.reportValidity()) return;

        const payload = {
            email: state.draft.email,
            comment: state.draft.comment.trim() || null,
        };

        const isCreating = state.editingId === null;

        state.saving = true;
        state.notice = "";
        clearError();
        render();

        try {
            if (isCreating) {
                await api.createFavoriteSender(payload);
            } else {
                await api.updateFavoriteSender(state.editingId, payload);
            }
        } catch (error) {
            console.error("Ошибка сохранения избранного", error);
            state.error = error.message || "Не удалось сохранить запись";
            state.saving = false;
            render();
            return;
        }

        state.saving = false;
        resetEditor();

        state.notice = isCreating
            ? "Адрес добавлен в общий список избранных."
            : "Изменения сохранены.";

        await loadPage();
    }

    async function deleteItem(senderId) {
        if (isBusy() || state.editorOpen) return;

        const item = state.items.find((entry) => entry.id === senderId);
        if (!item) return;

        const confirmed = window.confirm(
            `Удалить адрес ${item.email} из общего списка избранных?\n` +
            "Изменение будет действовать для всех пользователей. " +
            "Сами письма не будут удалены.",
        );

        if (!confirmed) return;

        clearSearchTimer();
        clearError();

        state.notice = "";
        state.saving = true;
        render();

        try {
            await api.deleteFavoriteSender(senderId);
        } catch (error) {
            console.error("Ошибка удаления избранного", error);
            state.error = error.message || "Не удалось удалить запись";
            state.saving = false;
            render();
            return;
        }

        state.saving = false;
        state.notice = "Адрес удалён из общего списка избранных.";

        await loadPage();
    }

    function handleSearchInput(event) {
        if (state.editorOpen || state.saving) return;

        state.search = String(event.target.value || "").trim();
        state.notice = "";

        clearSearchTimer();
        invalidateRequest();

        state.loading = false;
        state.loadingMore = false;

        // Старый курсор относится к предыдущему поиску.
        state.nextCursor = null;
        state.hasMore = false;

        clearError();
        render();

        state.searchTimer = setTimeout(() => {
            state.searchTimer = null;
            loadPage();
        }, SEARCH_DELAY_MS);
    }

    function clearSearch() {
        if (state.saving || state.editorOpen) return;

        const { searchInput } = getElements();

        clearSearchTimer();

        searchInput.value = "";
        state.search = "";
        state.notice = "";

        loadPage();
        searchInput.focus();
    }

    function bindEvents() {
        const elements = getElements();

        elements.addButton.addEventListener("click", beginCreate);

        elements.searchInput.addEventListener("input", handleSearchInput);
        elements.searchClear.addEventListener("click", clearSearch);

        elements.loadMoreButton.addEventListener("click", () => {
            loadPage(true);
        });

        elements.retryButton.addEventListener("click", () => {
            loadPage(state.retryMode === "more");
        });

        elements.tableBody.addEventListener("input", (event) => {
            const field = event.target.dataset.favoriteField;

            if (
                state.editorOpen &&
                !state.saving &&
                (field === "email" || field === "comment")
            ) {
                state.draft[field] = event.target.value;
            }
        });

        elements.tableBody.addEventListener("click", (event) => {
            const button = event.target.closest("[data-favorite-action]");
            if (!button || button.disabled) return;

            const action = button.dataset.favoriteAction;
            const senderId = Number(button.dataset.favoriteId);

            if (action === "save") {
                saveEditor();
            } else if (action === "cancel") {
                cancelEditor();
            } else if (action === "edit") {
                beginEdit(senderId);
            } else if (action === "delete") {
                deleteItem(senderId);
            }
        });

        elements.tableBody.addEventListener("keydown", (event) => {
            if (
                !event.target.matches("[data-favorite-field]") ||
                event.isComposing
            ) {
                return;
            }

            if (event.key === "Escape") {
                event.preventDefault();
                cancelEditor();
            } else if (
                event.key === "Enter" &&
                event.target.dataset.favoriteField === "email"
            ) {
                event.preventDefault();
                saveEditor();
            }
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindEvents();
        render();
        loadPage();
    });

    window.addEventListener("pagehide", () => {
        clearSearchTimer();
        invalidateRequest();
        state.loading = false;
        state.loadingMore = false;
    });

    window.addEventListener("pageshow", (event) => {
        if (event.persisted && !state.editorOpen && !state.saving) {
            loadPage();
        }
    });
})();