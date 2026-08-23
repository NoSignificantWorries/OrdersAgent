(function () {
    const PAGE_LIMIT = 50;
    const SEARCH_DEBOUNCE_MS = 350;
    const MIN_SEARCH_LENGTH = 2;

    const formatters = window.MailFormatters || {};

    const escapeHtml =
        typeof formatters.escapeHtml === "function"
            ? formatters.escapeHtml
            : (value) =>
                String(value ?? "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#39;");

    const escapeAttr =
        typeof formatters.escapeAttr === "function"
            ? formatters.escapeAttr
            : escapeHtml;

    const state = {
        items: [],
        nextCursor: null,
        hasMore: false,

        currentSearch: "",
        activeSearch: "",

        loading: false,
        loadingMore: false,
        creating: false,
        savingSource: null,

        editingSource: null,
        editingOriginal: null,

        requestController: null,
        requestSequence: 0,
        searchDebounceTimer: null,

        initialized: false,
        eventsBound: false,
    };

    function getElements() {
        return {
            addButton: document.getElementById("materials-add-btn"),
            searchInput: document.getElementById("materials-search-input"),
            searchClearButton: document.getElementById("materials-search-clear-btn"),
            status: document.getElementById("materials-status"),
            tableBody: document.getElementById("materials-table-body"),
            emptyState: document.getElementById("materials-empty-state"),
            loadMoreButton: document.getElementById("materials-load-more-btn"),
        };
    }

    function normalizeText(value) {
        return String(value || "").trim();
    }

    function getSearchValueForRequest(value) {
        const normalizedValue = normalizeText(value);

        if (normalizedValue.length < MIN_SEARCH_LENGTH) {
            return "";
        }

        return normalizedValue;
    }

    function getStatusText() {
        if (state.loading) {
            return "Загрузка материалов...";
        }

        if (state.loadingMore) {
            return "Загрузка следующей части списка...";
        }

        if (state.activeSearch) {
            return `Поиск: «${state.activeSearch}»`;
        }

        return "";
    }

    function renderStatus() {
        const { status } = getElements();
        if (!status) return;

        status.textContent = getStatusText();
        status.hidden = status.textContent === "";
    }

    function renderEmptyState() {
        const { emptyState } = getElements();
        if (!emptyState) return;

        const shouldShow =
            !state.loading &&
            !state.loadingMore &&
            state.items.length === 0 &&
            !state.creating;

        emptyState.hidden = !shouldShow;

        if (!shouldShow) {
            emptyState.innerHTML = "";
            return;
        }

        if (state.activeSearch) {
            emptyState.innerHTML = `
                <div class="materials-empty-title">Ничего не найдено</div>
                <div class="materials-empty-text">
                    По запросу «${escapeHtml(state.activeSearch)}» материалы не найдены.
                </div>
            `;
            return;
        }

        emptyState.innerHTML = `
            <div class="materials-empty-title">Материалы отсутствуют</div>
            <div class="materials-empty-text">
                Добавьте первое соответствие кнопкой «Добавить материал».
            </div>
        `;
    }

    function renderLoadMoreButton() {
        const { loadMoreButton } = getElements();
        if (!loadMoreButton) return;

        const shouldShow =
            state.hasMore &&
            !state.loading &&
            state.items.length > 0;

        loadMoreButton.hidden = !shouldShow;
        loadMoreButton.disabled = state.loadingMore || state.savingSource !== null;

        if (state.loadingMore) {
            loadMoreButton.textContent = "Загрузка...";
            return;
        }

        loadMoreButton.textContent = "Показать ещё";
    }

    function renderCreateRow() {
        if (!state.creating) {
            return "";
        }

        return `
            <tr class="materials-row materials-create-row">
                <td>
                    <input
                        type="text"
                        class="materials-input"
                        data-material-create-field="source"
                        maxlength="255"
                        placeholder="Материал заказчика"
                        aria-label="Материал заказчика"
                    >
                </td>

                <td>
                    <input
                        type="text"
                        class="materials-input"
                        data-material-create-field="target"
                        maxlength="255"
                        placeholder="Материал в системе"
                        aria-label="Материал в системе"
                    >
                </td>

                <td>
                    <input
                        type="text"
                        class="materials-input"
                        data-material-create-field="article"
                        maxlength="255"
                        placeholder="Артикул"
                        aria-label="Артикул"
                    >
                </td>

                <td class="materials-actions-cell">
                    <div class="materials-actions">
                        <button
                            type="button"
                            class="materials-save-btn"
                            data-material-action="create-save"
                            ${state.savingSource === "__create__" ? "disabled" : ""}
                        >
                            ${state.savingSource === "__create__" ? "Сохранение..." : "Сохранить"}
                        </button>

                        <button
                            type="button"
                            class="materials-cancel-btn"
                            data-material-action="create-cancel"
                            ${state.savingSource === "__create__" ? "disabled" : ""}
                        >
                            Отмена
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    function renderMappingRow(item) {
        const source = normalizeText(item?.source);
        const target = normalizeText(item?.target);
        const article = normalizeText(item?.article);

        const isEditing = state.editingSource === source;
        const isSaving = state.savingSource === source;
        const controlsDisabled =
            state.savingSource !== null &&
            state.savingSource !== source;

        if (isEditing) {
            return `
                <tr class="materials-row is-editing">
                    <td class="materials-source-cell">
                        <span class="materials-source-value">${escapeHtml(source)}</span>
                    </td>

                    <td>
                        <input
                            type="text"
                            class="materials-input"
                            data-material-edit-field="target"
                            maxlength="255"
                            value="${escapeAttr(target)}"
                            aria-label="Материал в системе для ${escapeAttr(source)}"
                            ${isSaving ? "disabled" : ""}
                        >
                    </td>

                    <td>
                        <input
                            type="text"
                            class="materials-input"
                            data-material-edit-field="article"
                            maxlength="255"
                            value="${escapeAttr(article)}"
                            aria-label="Артикул для ${escapeAttr(source)}"
                            ${isSaving ? "disabled" : ""}
                        >
                    </td>

                    <td class="materials-actions-cell">
                        <div class="materials-actions">
                            <button
                                type="button"
                                class="materials-save-btn"
                                data-material-action="save"
                                data-material-source="${escapeAttr(source)}"
                                ${isSaving ? "disabled" : ""}
                            >
                                ${isSaving ? "Сохранение..." : "Сохранить"}
                            </button>

                            <button
                                type="button"
                                class="materials-cancel-btn"
                                data-material-action="cancel"
                                data-material-source="${escapeAttr(source)}"
                                ${isSaving ? "disabled" : ""}
                            >
                                Отмена
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }

        return `
            <tr class="materials-row">
                <td class="materials-source-cell">${escapeHtml(source)}</td>
                <td>${escapeHtml(target)}</td>
                <td>${escapeHtml(article)}</td>

                <td class="materials-actions-cell">
                    <button
                        type="button"
                        class="materials-edit-btn"
                        data-material-action="edit"
                        data-material-source="${escapeAttr(source)}"
                        aria-label="Редактировать материал ${escapeAttr(source)}"
                        title="Редактировать"
                        ${controlsDisabled ? "disabled" : ""}
                    >
                        ✏️
                    </button>
                </td>
            </tr>
        `;
    }

    function renderTable() {
        const { tableBody } = getElements();
        if (!tableBody) return;

        const rows = [
            renderCreateRow(),
            ...state.items.map((item) => renderMappingRow(item)),
        ];

        if (state.loading && state.items.length === 0 && !state.creating) {
            tableBody.innerHTML = `
                <tr class="materials-row">
                    <td colspan="4" class="materials-loading-cell">
                        Загрузка материалов...
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = rows.join("");
    }

    function render() {
        renderStatus();
        renderTable();
        renderEmptyState();
        renderLoadMoreButton();
        updateSearchClearButton();
    }

    function updateSearchClearButton() {
        const { searchInput, searchClearButton } = getElements();
        if (!searchInput || !searchClearButton) return;

        searchClearButton.hidden = normalizeText(searchInput.value) === "";
    }

    function cancelActiveRequest() {
        if (state.requestController) {
            state.requestController.abort();
            state.requestController = null;
        }
    }

    function clearSearchDebounce() {
        if (state.searchDebounceTimer) {
            clearTimeout(state.searchDebounceTimer);
            state.searchDebounceTimer = null;
        }
    }

    function isAbortError(error) {
        return error?.name === "AbortError";
    }

    async function loadFirstPage({ showLoading = true } = {}) {
        cancelActiveRequest();

        state.requestSequence += 1;
        const requestSequence = state.requestSequence;

        const controller = new AbortController();
        state.requestController = controller;

        state.activeSearch = getSearchValueForRequest(state.currentSearch);
        state.nextCursor = null;
        state.hasMore = false;

        if (showLoading) {
            state.items = [];
        }

        state.loading = true;
        state.loadingMore = false;
        render();

        try {
            const result = await window.MaterialsApi.loadMappings({
                cursor: null,
                limit: PAGE_LIMIT,
                search: state.activeSearch,
                signal: controller.signal,
            });

            if (requestSequence !== state.requestSequence) {
                return;
            }

            state.items = Array.isArray(result?.items) ? result.items : [];
            state.nextCursor = result?.next_cursor || null;
            state.hasMore = result?.has_more === true;
        } catch (error) {
            if (isAbortError(error)) {
                return;
            }

            console.error("Не удалось загрузить материалы", error);

            if (requestSequence === state.requestSequence) {
                state.items = [];
                state.nextCursor = null;
                state.hasMore = false;
                showLoadError(error.message || "Не удалось загрузить материалы");
            }
        } finally {
            if (requestSequence === state.requestSequence) {
                state.loading = false;
                state.requestController = null;
                render();
            }
        }
    }

    async function loadMore() {
        if (
            state.loading ||
            state.loadingMore ||
            !state.hasMore ||
            !state.nextCursor
        ) {
            return;
        }

        cancelActiveRequest();

        state.requestSequence += 1;
        const requestSequence = state.requestSequence;

        const controller = new AbortController();
        state.requestController = controller;
        state.loadingMore = true;
        render();

        try {
            const result = await window.MaterialsApi.loadMappings({
                cursor: state.nextCursor,
                limit: PAGE_LIMIT,
                search: state.activeSearch,
                signal: controller.signal,
            });

            if (requestSequence !== state.requestSequence) {
                return;
            }

            const nextItems = Array.isArray(result?.items) ? result.items : [];

            state.items = [...state.items, ...nextItems];
            state.nextCursor = result?.next_cursor || null;
            state.hasMore = result?.has_more === true;
        } catch (error) {
            if (isAbortError(error)) {
                return;
            }

            console.error("Не удалось загрузить следующую часть материалов", error);
            showLoadError(
                error.message || "Не удалось загрузить следующую часть материалов",
            );
        } finally {
            if (requestSequence === state.requestSequence) {
                state.loadingMore = false;
                state.requestController = null;
                render();
            }
        }
    }

    function showLoadError(message) {
        const { emptyState } = getElements();
        if (!emptyState) {
            alert(message);
            return;
        }

        emptyState.hidden = false;
        emptyState.innerHTML = `
            <div class="materials-error-title">Ошибка загрузки</div>
            <div class="materials-empty-text">${escapeHtml(message)}</div>
            <button
                type="button"
                class="materials-retry-btn"
                data-material-action="retry-load"
            >
                Повторить
            </button>
        `;
    }

    function beginCreate() {
        if (state.loading || state.savingSource !== null) {
            return;
        }

        state.creating = true;
        state.editingSource = null;
        state.editingOriginal = null;
        render();

        const sourceInput = document.querySelector(
            '[data-material-create-field="source"]',
        );

        if (sourceInput) {
            sourceInput.focus();
        }
    }

    function cancelCreate() {
        if (state.savingSource === "__create__") {
            return;
        }

        state.creating = false;
        render();
    }

    function beginEdit(source) {
        if (
            !source ||
            state.loading ||
            state.savingSource !== null ||
            state.creating
        ) {
            return;
        }

        const item = state.items.find(
            (candidate) => normalizeText(candidate?.source) === source,
        );

        if (!item) {
            alert("Не удалось найти материал для редактирования");
            return;
        }

        state.editingSource = source;
        state.editingOriginal = {
            source,
            target: normalizeText(item.target),
            article: normalizeText(item.article),
        };

        render();

        const targetInput = document.querySelector(
            '[data-material-edit-field="target"]',
        );

        if (targetInput) {
            targetInput.focus();
            targetInput.select();
        }
    }

    function cancelEdit() {
        if (state.savingSource !== null) {
            return;
        }

        state.editingSource = null;
        state.editingOriginal = null;
        render();
    }

    function readCreatePayload() {
        const sourceInput = document.querySelector(
            '[data-material-create-field="source"]',
        );
        const targetInput = document.querySelector(
            '[data-material-create-field="target"]',
        );
        const articleInput = document.querySelector(
            '[data-material-create-field="article"]',
        );

        return {
            source: normalizeText(sourceInput?.value),
            target: normalizeText(targetInput?.value),
            article: normalizeText(articleInput?.value),
        };
    }

    function readUpdatePayload(source) {
        const targetInput = document.querySelector(
            '[data-material-edit-field="target"]',
        );
        const articleInput = document.querySelector(
            '[data-material-edit-field="article"]',
        );

        return {
            source,
            target: normalizeText(targetInput?.value),
            article: normalizeText(articleInput?.value),
        };
    }

    function validatePayload(payload) {
        if (!payload.source) {
            throw new Error("Заполните поле «Материал заказчика»");
        }

        if (!payload.target) {
            throw new Error("Заполните поле «Материал в системе»");
        }

        if (!payload.article) {
            throw new Error("Заполните поле «Артикул»");
        }

        if (
            payload.source.length > 255 ||
            payload.target.length > 255 ||
            payload.article.length > 255
        ) {
            throw new Error("Длина каждого поля не должна превышать 255 символов");
        }
    }

    async function saveCreate() {
        if (state.savingSource !== null) {
            return;
        }

        let payload;

        try {
            payload = readCreatePayload();
            validatePayload(payload);
        } catch (error) {
            alert(error.message || "Проверьте введённые данные");
            return;
        }

        state.savingSource = "__create__";
        render();

        try {
            await window.MaterialsApi.createMapping(payload);

            state.creating = false;
            state.savingSource = null;

            await loadFirstPage({ showLoading: true });
        } catch (error) {
            console.error("Не удалось создать материал", error);
            alert(error.message || "Не удалось добавить материал");
        } finally {
            if (state.savingSource === "__create__") {
                state.savingSource = null;
                render();
            }
        }
    }

    async function saveEdit(source) {
        if (
            !source ||
            state.editingSource !== source ||
            state.savingSource !== null
        ) {
            return;
        }

        let payload;

        try {
            payload = readUpdatePayload(source);
            validatePayload(payload);
        } catch (error) {
            alert(error.message || "Проверьте введённые данные");
            return;
        }

        state.savingSource = source;
        render();

        try {
            const updatedItem = await window.MaterialsApi.updateMapping(payload);

            state.items = state.items.map((item) =>
                normalizeText(item?.source) === source
                    ? updatedItem
                    : item,
            );

            state.editingSource = null;
            state.editingOriginal = null;
        } catch (error) {
            console.error("Не удалось сохранить материал", error);
            alert(error.message || "Не удалось сохранить материал");
        } finally {
            state.savingSource = null;
            render();
        }
    }

    function handleTableClick(event) {
        const actionTarget = event.target.closest("[data-material-action]");
        if (!actionTarget) return;

        const action = actionTarget.dataset.materialAction;
        const source = normalizeText(actionTarget.dataset.materialSource);

        if (action === "edit") {
            beginEdit(source);
            return;
        }

        if (action === "cancel") {
            cancelEdit();
            return;
        }

        if (action === "save") {
            saveEdit(source);
            return;
        }

        if (action === "create-save") {
            saveCreate();
            return;
        }

        if (action === "create-cancel") {
            cancelCreate();
            return;
        }

        if (action === "retry-load") {
            loadFirstPage({ showLoading: true });
        }
    }

    function handleTableKeydown(event) {
        const input = event.target.closest(
            "[data-material-edit-field], [data-material-create-field]",
        );

        if (!input) {
            return;
        }

        if (event.key === "Escape") {
            event.preventDefault();

            if (state.creating) {
                cancelCreate();
            } else {
                cancelEdit();
            }

            return;
        }

        if (event.key !== "Enter") {
            return;
        }

        event.preventDefault();

        if (state.creating) {
            saveCreate();
            return;
        }

        if (state.editingSource) {
            saveEdit(state.editingSource);
        }
    }

    function handleSearchInput(event) {
        state.currentSearch = String(event.target.value || "");
        updateSearchClearButton();

        clearSearchDebounce();

        state.searchDebounceTimer = setTimeout(() => {
            state.searchDebounceTimer = null;
            loadFirstPage({ showLoading: true });
        }, SEARCH_DEBOUNCE_MS);
    }

    function clearSearch() {
        const { searchInput } = getElements();
        if (!searchInput) return;

        searchInput.value = "";
        state.currentSearch = "";
        clearSearchDebounce();
        updateSearchClearButton();
        loadFirstPage({ showLoading: true });
        searchInput.focus();
    }

    function bindEvents() {
        if (state.eventsBound) {
            return;
        }

        const {
            addButton,
            searchInput,
            searchClearButton,
            tableBody,
            emptyState,
            loadMoreButton,
        } = getElements();

        addButton?.addEventListener("click", beginCreate);
        searchInput?.addEventListener("input", handleSearchInput);
        searchClearButton?.addEventListener("click", clearSearch);

        tableBody?.addEventListener("click", handleTableClick);
        tableBody?.addEventListener("keydown", handleTableKeydown);

        emptyState?.addEventListener("click", handleTableClick);
        loadMoreButton?.addEventListener("click", loadMore);

        state.eventsBound = true;
    }

    async function init() {
        if (state.initialized) {
            return;
        }

        state.initialized = true;
        state.currentSearch = "";
        state.activeSearch = "";
        state.items = [];
        state.nextCursor = null;
        state.hasMore = false;
        state.creating = false;
        state.editingSource = null;
        state.editingOriginal = null;

        bindEvents();
        render();

        await loadFirstPage({ showLoading: true });
    }

    function destroy() {
        clearSearchDebounce();
        cancelActiveRequest();

        state.requestSequence += 1;
        state.items = [];
        state.nextCursor = null;
        state.hasMore = false;
        state.currentSearch = "";
        state.activeSearch = "";
        state.loading = false;
        state.loadingMore = false;
        state.creating = false;
        state.savingSource = null;
        state.editingSource = null;
        state.editingOriginal = null;
        state.initialized = false;

        const { tableBody, emptyState, status, loadMoreButton } = getElements();

        if (tableBody) {
            tableBody.replaceChildren();
        }

        if (emptyState) {
            emptyState.innerHTML = "";
            emptyState.hidden = true;
        }

        if (status) {
            status.textContent = "";
            status.hidden = true;
        }

        if (loadMoreButton) {
            loadMoreButton.hidden = true;
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        init();
    });

    window.addEventListener("pagehide", () => {
        destroy();
    });

    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            init();
        }
    });

    window.MaterialsPage = {
        init,
        destroy,
    };
})();