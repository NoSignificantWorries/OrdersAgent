(function () {
    const {
        escapeHtml,
        formatDate,
        formatTimeOnly,
    } = window.MailFormatters;

    function readSentStateFromUrl() {
        const params = new URLSearchParams(window.location.search);

        return {
            currentPage: Math.max(1, Number(params.get("page")) || 1),
            currentSearchTerm: params.get("search") || "",
            sortNewestFirst: params.get("sort") !== "oldest",
            selectedEmailId: Math.max(0, Number(params.get("selected_email_id")) || 0) || null,
            selectedSourceType: params.get("selected_source") || "sent",
        };
    }

   function buildSentHistoryState(state) {
        return {
            currentPage: Math.max(1, Number(state.currentPage) || 1),
            currentSearchTerm: String(state.currentSearchTerm || ""),
            sortNewestFirst: state.sortNewestFirst !== false,
            selectedEmailId:
                state.selectedEmailId != null ? Number(state.selectedEmailId) : null,
            selectedSourceType: String(state.selectedSourceType || "sent"),
        };
    }

    function writeSentStateToUrl(state, mode = "replace") {
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

        if (state.selectedEmailId != null && Number(state.selectedEmailId) > 0) {
            params.set("selected_email_id", String(state.selectedEmailId));
            params.set("selected_source", String(state.selectedSourceType || "sent"));
        }

        const query = params.toString();
        const nextUrl = query
            ? `${window.location.pathname}?${query}`
            : window.location.pathname;

        const historyState = buildSentHistoryState(state);

        if (mode === "push") {
            window.history.pushState(historyState, "", nextUrl);
            return;
        }

        window.history.replaceState(historyState, "", nextUrl);
    }

    function syncSentState(state, mode = "replace") {
        writeSentStateToUrl(state, mode);
        updateSentSectionNavLinks(state);
    }

    async function restoreSentStateFromHistory(state, historyState = null) {
        const urlState = readSentStateFromUrl();
        const sourceState =
            historyState && typeof historyState === "object"
                ? historyState
                : {};

        state.currentPage = Math.max(
            1,
            Number(sourceState.currentPage ?? urlState.currentPage) || 1,
        );
        state.currentSearchTerm = String(
            sourceState.currentSearchTerm ?? urlState.currentSearchTerm ?? "",
        );
        state.sortNewestFirst =
            sourceState.sortNewestFirst ?? urlState.sortNewestFirst ?? true;

        const nextSelectedSourceType = String(
            sourceState.selectedSourceType ?? urlState.selectedSourceType ?? "sent",
        );
        const nextSelectedEmailIdRaw =
            sourceState.selectedEmailId ?? urlState.selectedEmailId ?? null;
        const nextSelectedEmailId = Number(nextSelectedEmailIdRaw || 0);

        state.selectedSourceType = nextSelectedSourceType;
        state.selectedEmailId =
            nextSelectedSourceType === "sent" && Number.isFinite(nextSelectedEmailId) && nextSelectedEmailId > 0
                ? nextSelectedEmailId
                : null;

        const searchInput = document.getElementById("search-input");
        if (searchInput && searchInput.value !== state.currentSearchTerm) {
            searchInput.value = state.currentSearchTerm;
        }

        const newestBtn = document.getElementById("sort-newest-btn");
        const oldestBtn = document.getElementById("sort-oldest-btn");
        if (newestBtn && oldestBtn) {
            newestBtn.classList.toggle("active", state.sortNewestFirst === true);
            oldestBtn.classList.toggle("active", state.sortNewestFirst === false);
        }

        await loadSentEmails(state);
        renderSentEmailList(state);
        renderSentPagination(state);

        if (state.selectedSourceType === "sent" && state.selectedEmailId != null) {
            const existingEmail = state.emails.find(
                (email) => Number(email.email_id || email.id) === Number(state.selectedEmailId),
            );

            if (existingEmail) {
                await selectSentEmail(existingEmail.id, state, { historyMode: "replace" });
                return;
            }

            try {
                const detailEmail = await loadSentEmailDetail(state.selectedEmailId);
                const mergedEmail = mergeSentEmailDetailIntoState(detailEmail, state);

                if (!state.emails.some((email) => Number(email.id) === Number(mergedEmail.id))) {
                    state.emails.unshift(mergedEmail);
                    renderSentEmailList(state);
                }

                await selectSentEmail(mergedEmail.id, state, { historyMode: "replace" });
                return;
            } catch (detailError) {
                console.error("Не удалось восстановить исходящее письмо из истории", detailError);
            }
        }

        highlightSelectedEmail(null);
        const emailView = document.getElementById("emailView");
        if (emailView) {
            emailView.innerHTML =
                '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
        }
    }

    function updateSentSectionNavLinks(state) {
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

                link.href = params.toString()
                    ? `${url.pathname}?${params.toString()}`
                    : url.pathname;
            } catch (error) {
                console.error("Не удалось обновить ссылку раздела (sent)", error);
            }
        });
    }

    function openInboxThreadEmailFromSent(threadEmail, state) {
        const targetEmailId = Number(
            threadEmail?.email_id ||
            threadEmail?.emailid ||
            threadEmail?.source_id ||
            0,
        );

        if (!Number.isFinite(targetEmailId) || targetEmailId <= 0) {
            alert("Не удалось определить входящее письмо для перехода.");
            return;
        }

        const targetPageType = threadEmail?.archived === true ? "archived" : "inbox";

        const params = new URLSearchParams();

        if (String(state.currentSearchTerm || "").trim()) {
            params.set("search", String(state.currentSearchTerm).trim());
        }

        if (state.sortNewestFirst === false) {
            params.set("sort", "oldest");
        }

        params.set("selected_email_id", String(targetEmailId));
        params.set("selected_source", targetPageType);

        window.location.href = `/${targetPageType}?${params.toString()}`;
    }

    function normalizeDocuments(raw) {
        if (!raw) return [];

        if (Array.isArray(raw)) {
            return raw.filter((item) => item && typeof item === "object");
        }

        if (typeof raw === "string") {
            try {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) {
                    return parsed.filter((item) => item && typeof item === "object");
                }
                if (parsed && typeof parsed === "object") {
                    return [parsed];
                }
            } catch (e) {
                return [];
            }
            return [];
        }

        if (raw && typeof raw === "object") {
            return [raw];
        }

        return [];
    }

    function normalizeSentItem(item) {
        const subject = item.emailsubject || "(без темы)";
        const sender = item.emailfrom || item.mailbox || "";
        const recipient = item.toheader || "";
        const date = item.sentat || item.emaildate || item.createdat || null;

        return {
            id: Number(item.id || item.source_id || 0),                 // sent_emails.id
            email_id: Number(item.emailid || item.email_id || item.id), // parent_email_id
            source_id: Number(item.id || item.source_id || 0),
            subject,
            sender,
            mailbox: item.mailbox || "",
            recipient,
            to_header: item.toheader || "",
            cc_header: item.ccheader || "",
            bcc_header: item.bccheader || "",
            content: item.bodytext || item.rawemail || "",
            body_text: typeof item.bodytext === "string" ? item.bodytext : "",
            raw_email: typeof item.rawemail === "string" ? item.rawemail : "",
            date,
            read: true,
            archived: false,
            status: item.status || null,
            model_decision: item.modeldecision || null,
            predicted_class: item.predictedclass || null,
            prob_1: item.prob1 ?? null,
            message_id: item.messageid || item.message_id || "",
            in_reply_to: item.inreplyto || item.in_reply_to || "",
            references: item.references || "",
            documents: normalizeDocuments(item.documents),
            task: null,
            source_type: "sent",
        };
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

    async function loadSentThread(emailId) {
        const resp = await fetch(`/api/emails/${emailId}/thread?source=sent`, {
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let detail = `Не удалось загрузить цепочку (${resp.status})`;

            try {
                const data = await resp.json();
                if (data?.detail) {
                    detail = data.detail;
                }
            } catch (_) {}

            throw new Error(detail);
        }

        const data = await resp.json();
        return Array.isArray(data?.items) ? data.items : [];
    }

    async function loadSentEmailDetail(emailId) {
        const resp = await fetch(`/api/sent/${emailId}/detail`, {
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let detail = `Не удалось загрузить письмо (${resp.status})`;

            try {
                const data = await resp.json();
                if (data?.detail) {
                    detail = data.detail;
                }
            } catch (_) {}

            throw new Error(detail);
        }

        const data = await resp.json();
        if (!data?.item || typeof data.item !== "object") {
            throw new Error("Некорректный ответ деталей письма");
        }

        return normalizeSentItem(data.item);
    }

    function hasLoadedSentDetails(email) {
        if (!email || typeof email !== "object") return false;

        const hasRawEmail = typeof email.raw_email === "string" && email.raw_email.trim() !== "";
        const hasBodyText = typeof email.body_text === "string" && email.body_text.trim() !== "";
        const hasDocuments = Array.isArray(email.documents) && email.documents.length > 0;

        return hasRawEmail || hasBodyText || hasDocuments;
    }

    function mergeSentEmailDetailIntoState(detailEmail, state) {
        if (!detailEmail || !state || !Array.isArray(state.emails)) {
            return detailEmail;
        }

        const index = state.emails.findIndex((item) => Number(item.id) === Number(detailEmail.id));
        if (index === -1) {
            return detailEmail;
        }

        const merged = {
            ...state.emails[index],
            ...detailEmail,
            documents: normalizeDocuments(detailEmail.documents),
        };

        state.emails[index] = merged;
        return merged;
    }

    function extractDisplayBodyFromRawEmail(value) {
        const raw = String(value || "").replace(/\r\n/g, "\n");

        if (!raw.trim()) {
            return "";
        }

        const headerBodySeparator = raw.indexOf("\n\n");
        let body = headerBodySeparator >= 0 ? raw.slice(headerBodySeparator + 2) : raw;

        body = body
            .replace(/\n{3,}/g, "\n\n")
            .trim();

        return body;
    }

    function normalizeSentThreadItem(threadEmail) {
        const subject =
            threadEmail?.subject ||
            threadEmail?.emailsubject ||
            "(без темы)";

        const rawSource =
            threadEmail?.content ||
            threadEmail?.rawemail ||
            "";

        const rawText =
            threadEmail?.thread_source === "sent"
                ? extractDisplayBodyFromRawEmail(rawSource)
                : rawSource;

        const preview =
            threadEmail?.preview ||
            String(rawText)
                .replace(/\r/g, "\n")
                .replace(/\n{2,}/g, "\n")
                .replace(/\s+/g, " ")
                .trim();

        const date =
            threadEmail?.date ||
            threadEmail?.emaildate ||
            threadEmail?.createdat ||
            threadEmail?.sentat ||
            null;

        const sender =
            threadEmail?.sender ||
            threadEmail?.emailfrom ||
            "Без отправителя";

        const mailbox =
            threadEmail?.mailbox ||
            threadEmail?.toheader ||
            "";

        return {
            ...threadEmail,
            id: Number(threadEmail?.source_id || threadEmail?.id || threadEmail?.emailid),
            email_id: Number(threadEmail?.emailid || threadEmail?.email_id || 0),
            subject,
            content: rawText,
            preview,
            date,
            sender,
            mailbox,
            to_header: threadEmail?.to_header || threadEmail?.toheader || "",
            cc_header: threadEmail?.cc_header || threadEmail?.ccheader || "",
            bcc_header: threadEmail?.bcc_header || threadEmail?.bccheader || "",
            documents: normalizeDocuments(threadEmail?.documents),
            source_type: threadEmail?.thread_source || threadEmail?.source_type || "inbox",
            thread_source: threadEmail?.thread_source || threadEmail?.source_type || "inbox",
            source_id: Number(threadEmail?.source_id || threadEmail?.id || threadEmail?.emailid),
            message_id: threadEmail?.message_id || threadEmail?.messageid || "",
        };
    }

    function getVisiblePages(current, total, maxVisible = 7) {
    if (total <= maxVisible) {
        return Array.from({ length: total }, (_, i) => i + 1);
    }

    const pages = [];
    const middleCount = maxVisible - 4;
    const start = Math.max(2, current - Math.floor(middleCount / 2));
    const end = Math.min(total - 1, start + middleCount - 1);

    pages.push(1);

    if (start > 2) pages.push("dots");

    for (let i = start; i <= end; i += 1) {
        pages.push(i);
    }

    if (end < total - 1) pages.push("dots");

    pages.push(total);

    return pages;
}

async function reloadSentEmails(state) {
    await loadSentEmails(state);
    renderSentEmailList(state);
    renderSentPagination(state);
}

function renderSentPagination(state) {
    const root = document.getElementById("emails-pagination");
    const pagesRoot = document.getElementById("pagination-pages");
    const prevBtn = document.getElementById("pagination-prev-btn");
    const nextBtn = document.getElementById("pagination-next-btn");

    if (!root || !pagesRoot || !prevBtn || !nextBtn) return;

    if (state.totalPages <= 1) {
        root.hidden = true;
        pagesRoot.innerHTML = "";
        return;
    }

    root.hidden = false;
    pagesRoot.innerHTML = "";

    const visiblePages = getVisiblePages(state.currentPage, state.totalPages, 7);

    visiblePages.forEach((item) => {
        if (item === "dots") {
            const span = document.createElement("span");
            span.className = "pagination-dots";
            span.textContent = "…";
            pagesRoot.appendChild(span);
            return;
        }

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pagination-page-btn";
        btn.textContent = String(item);
        btn.setAttribute("aria-label", `Страница ${item}`);

        if (item === state.currentPage) {
            btn.classList.add("active");
            btn.setAttribute("aria-current", "page");
        }

        btn.addEventListener("click", async () => {
            if (item === state.currentPage) return;
            state.currentPage = item;
            state.selectedEmailId = null;
            state.selectedSourceType = "sent";
            syncSentState(state);
            await reloadSentEmails(state);
        });

        pagesRoot.appendChild(btn);
    });

    prevBtn.disabled = state.currentPage <= 1;
    nextBtn.disabled = state.currentPage >= state.totalPages;

    prevBtn.onclick = async () => {
        if (state.currentPage <= 1) return;
        state.currentPage -= 1;
        state.selectedEmailId = null;
        state.selectedSourceType = "sent";
        syncSentState(state);
        await reloadSentEmails(state);
    };

    nextBtn.onclick = async () => {
        if (state.currentPage >= state.totalPages) return;
        state.currentPage += 1;
        state.selectedEmailId = null;
        state.selectedSourceType = "sent";
        syncSentState(state);
        await reloadSentEmails(state);
    };
}

    function renderSentEmailList(state) {
        const container = document.getElementById("emailsContainer");
        if (!container) return;

        const filtered = [...state.emails];

        if (filtered.length === 0) {
            container.innerHTML =
                '<div class="email-placeholder" style="padding:20px;text-align:center;">Письма отсутствуют</div>';
            return;
        }

        container.innerHTML = filtered
            .map((email) => {
                const mailParityId = Number(email.email_id || email.id);
                const parityClass =
                    Number.isFinite(mailParityId) && mailParityId % 2 === 0
                        ? "email-item--even"
                        : "email-item--odd";

                return `
                    <div
                        class="email-item is-read ${parityClass}"
                        data-id="${email.id}"
                        data-email-id="${mailParityId}"
                    >
                        <div class="subject">${escapeHtml(email.subject)}</div>
                        <div class="email-item-header">
                            <div class="sender">От: ${escapeHtml(email.sender)}</div>
                        </div>
                        <div class="recipient">Кому: ${escapeHtml(email.recipient || "")}</div>
                        <div class="date">
                            ${formatDate(email.date)}
                            <span class="email-time">${formatTimeOnly(email.date)}</span>
                        </div>
                    </div>
                `;
            })
            .join("");

        document.querySelectorAll(".email-item").forEach((el) => {
            el.addEventListener("click", () =>
                selectSentEmail(Number(el.dataset.id), state, { historyMode: "push" })
            );
        });

        if (state.selectedEmailId != null) {
            highlightSelectedEmail(state.selectedEmailId);
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

    async function renderSentEmailCard(email, state) {
        const emailView = document.getElementById("emailView");
        if (!emailView) return;

        const docs = normalizeDocuments(email.documents);

        const realEmailId = email.id;
        state.selectedEmailSnapshot = email;

        let threadMessages = [];

        try {
            threadMessages = await loadSentThread(realEmailId);
        } catch (error) {
            console.error("Не удалось загрузить цепочку исходящего письма", error);
            threadMessages = [email];
        }

        threadMessages = threadMessages.map(normalizeSentThreadItem);

        const hasThread = threadMessages.length > 1;

        const threadExpanded = false;
        const threadChevron = threadExpanded ? "▼" : "▶";

        const currentThreadSource = email.source_type || "sent";
        const currentSourceId = email.id;

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
                                    const threadSource = String(threadEmail.thread_source || threadEmail.source_type || "inbox");
                                    const threadSourceId = Number(threadEmail.source_id || 0);

                                    const isCurrent =
                                        threadSource === String(currentThreadSource) &&
                                        threadSourceId === Number(currentSourceId);

                                    const previewSource =
                                        threadEmail.preview || threadEmail.content || threadEmail.rawemail || "";

                                    const preview = escapeHtml(String(previewSource).slice(0, 180));

                                    return `
                                        <button
                                            type="button"
                                            class="email-thread-item ${isCurrent ? "is-current" : ""}"
                                            data-thread-source="${escapeHtml(threadSource)}"
                                            data-thread-source-id="${escapeHtml(String(threadSourceId))}"
                                        >
                                            <span class="email-thread-marker" aria-hidden="true"></span>

                                            <span class="email-thread-item-main">
                                                <span class="email-thread-item-top">
                                                    <span class="email-thread-sender">${
                                                        threadEmail.thread_source === "sent"
                                                            ? `Исходящее: ${escapeHtml(threadEmail.sender || threadEmail.emailfrom || "Без отправителя")}`
                                                            : `Входящее: ${escapeHtml(threadEmail.sender || threadEmail.emailfrom || "Без отправителя")}`
                                                    }</span>
                                                    ${
                                                        isCurrent
                                                            ? '<span class="email-thread-current-badge">Текущее</span>'
                                                            : ""
                                                    }
                                                </span>

                                                <span class="email-thread-item-meta">
                                                    ${threadEmail.date ? `${escapeHtml(formatDate(threadEmail.date))} ${escapeHtml(formatTimeOnly(threadEmail.date))}` : "Дата неизвестна"}
                                                </span>

                                                <span class="email-thread-item-subject">
                                                    ${escapeHtml(threadEmail.subject || threadEmail.emailsubject || "(без темы)")}
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

        const bodySource = String(email.body_text || email.content || email.raw_email || "")
            .replace(/\r\n/g, "\n")
            .trim();

        const formattedContent =
            bodySource
                .split("\n")
                .map((line) => {
                    if (line.trim() === "") return "<br>";
                    if (line.includes("•")) {
                        return `<p style="margin-left:20px;">${escapeHtml(line)}</p>`;
                    }
                    return `<p>${escapeHtml(line)}</p>`;
                })
                .join("") || "<p>...</p>";

        const attachmentsHtml = docs.length
            ? `
                <div class="email-attachments">
                    <strong>Вложения:</strong>
                    <ul>
                        ${docs
                            .map((doc) => {
                                const filename =
                                    doc.document_name ||
                                    doc.filename ||
                                    `attachment-${doc.id || ""}`;
                                return `
                                    <li>${escapeHtml(filename)}</li>
                                `;
                            })
                            .join("")}
                    </ul>
                    <button
                        type="button"
                        class="save-all-attachments-btn"
                        data-email-id="${email.id}"
                    >
                        ${docs.length === 1 ? "Скачать" : "Скачать все"}
                    </button>
                </div>
            `
            : "";

            const actionsHtml = `
                <div class="reply-block">
                    <div class="email-bottom-actions sent-email-bottom-actions">
                        <div class="email-bottom-actions-inner">
                            <div class="email-bottom-actions-left">
                                <button
                                    type="button"
                                    id="forward-toggle-btn"
                                    class="reply-btn reply-btn-primary"
                                >
                                    Переслать
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

        emailView.innerHTML = `
            <div class="email-card sent-email-card">
                <div class="email-card-header">
                    <h2 class="email-subject">${escapeHtml(email.subject)}</h2>
                    <div class="email-meta">
                        <div><strong>От:</strong> ${escapeHtml(email.sender || "")}</div>
                        <div><strong>Кому:</strong> ${escapeHtml(email.to_header || email.recipient || "")}</div>
                        ${email.cc_header ? `<div><strong>Копия:</strong> ${escapeHtml(email.cc_header)}</div>` : ""}
                        ${email.bcc_header ? `<div><strong>Скрытая копия:</strong> ${escapeHtml(email.bcc_header)}</div>` : ""}
                        <div><strong>Дата:</strong> ${escapeHtml(formatDate(email.date))} ${escapeHtml(formatTimeOnly(email.date))}</div>
                    </div>
                </div>

                ${threadBlock}
                ${attachmentsHtml}

                <div class="email-body">
                    ${formattedContent}
                </div>

                ${actionsHtml}

            </div>
        `;

        const saveAttachmentsBtn = emailView.querySelector(".save-all-attachments-btn");
        if (saveAttachmentsBtn) {
            saveAttachmentsBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const emailId = saveAttachmentsBtn.dataset.emailId;
                window.location.href = `/api/sent/${emailId}/attachments/download-all`;
            });
        }

        const threadToggleBtn = emailView.querySelector(`#thread-toggle-btn-${email.id}`);
        const threadPanelElement = emailView.querySelector(`#email-thread-panel-${email.id}`);

        if (threadToggleBtn && threadPanelElement) {
            threadToggleBtn.addEventListener("click", () => {
                const expanded = threadToggleBtn.getAttribute("aria-expanded") === "true";
                const nextExpanded = !expanded;

                threadToggleBtn.setAttribute("aria-expanded", nextExpanded ? "true" : "false");

                const icon = threadToggleBtn.querySelector(".email-thread-toggle-icon");
                if (icon) {
                    icon.textContent = nextExpanded ? "▼" : "▶";
                }

                threadPanelElement.hidden = !nextExpanded;
            });
        }

        const threadPanel = emailView.querySelector(".email-thread-panel");
        if (threadPanel) {
            threadPanel.addEventListener("click", async (event) => {
                const target = event.target.closest("[data-thread-source][data-thread-source-id]");
                if (!target) return;

                event.stopPropagation();

                const targetSource = String(target.dataset.threadSource || "");
                const targetSourceId = Number(target.dataset.threadSourceId || 0);

                if (!targetSource || !Number.isFinite(targetSourceId) || targetSourceId <= 0) {
                    return;
                }

                const isCurrentEmail =
                    targetSource === String(currentThreadSource) &&
                    targetSourceId === Number(currentSourceId);

                if (isCurrentEmail) {
                    return;
                }

                const targetThreadEmail = threadMessages.find(
                    (item) =>
                        String(item.thread_source || item.source_type || "inbox") === targetSource &&
                        Number(item.source_id || 0) === targetSourceId,
                );

                if (!targetThreadEmail) {
                    alert("Не удалось найти письмо в цепочке.");
                    return;
                }

                if (targetSource === "sent") {
                    const targetEmail = state.emails.find(
                        (e) => Number(e.id) === targetSourceId,
                    );

                    if (targetEmail) {
                        await selectSentEmail(targetEmail.id, state, { historyMode: "push" });
                        return;
                    }

                    state.selectedEmailId = targetSourceId;
                    state.selectedSourceType = "sent";
                    syncSentState(state);

                    try {
                        const detailEmail = await loadSentEmailDetail(targetSourceId);
                        const mergedEmail = mergeSentEmailDetailIntoState(detailEmail, state);

                        if (!state.emails.some((e) => Number(e.id) === Number(mergedEmail.id))) {
                            state.emails.unshift(mergedEmail);
                            renderSentEmailList(state);
                        }

                        await selectSentEmail(targetSourceId, state, { historyMode: "push" });
                        return;
                    } catch (error) {
                        console.error("Не удалось загрузить исходящее письмо из цепочки", error);
                        alert("Не удалось открыть исходящее письмо из цепочки.");
                        return;
                    }
                }

                if (targetSource === "inbox") {
                    openInboxThreadEmailFromSent(targetThreadEmail, state);
                    return;
                }

                alert("Неизвестный тип письма в цепочке.");
            });
        }

        const forwardToggleBtn = emailView.querySelector("#forward-toggle-btn");
            if (forwardToggleBtn) {
                forwardToggleBtn.addEventListener("click", async () => {
                    forwardToggleBtn.disabled = true;

                    try {
                        //const realEmailId = email.email_id || email.id;

                        if (typeof window.MailPage?.openForwardCompose === "function") {
                            await window.MailPage.openForwardCompose({ emailId: realEmailId });
                        } else if (typeof window.MailCompose?.openForwardCompose === "function") {
                            await window.MailCompose.openForwardCompose(state.composeDeps, {
                                emailId: realEmailId,
                            });
                        } else {
                            throw new Error("Форма пересылки не подключена");
                        }
                    } catch (e) {
                        console.error(e);
                        alert(e.message || "Не удалось открыть форму пересылки");
                    } finally {
                        forwardToggleBtn.disabled = false;
                    }
                });
            }
    }

    async function selectSentEmail(id, state, options = {}) {
        const {
            historyMode = "push",
        } = options;

        state.selectedEmailId = Number(id);
        state.selectedSourceType = "sent";
        syncSentState(state, historyMode);

        let email = state.emails.find(
            (e) => Number(e.email_id || e.id) === Number(id),
        );

        let fromList = true;

        if (!email) {
            fromList = false;
            try {
                const detailEmail = await loadSentEmailDetail(id);
                email = mergeSentEmailDetailIntoState(detailEmail, state);

                if (!state.emails.some((e) => Number(e.id) === Number(email.id))) {
                    state.emails.unshift(email);
                    renderSentEmailList(state);
                }

                state.selectedEmailSnapshot = email;
            } catch (detailError) {
                console.error("Не удалось загрузить детали исходящего письма", detailError);
                return;
            }
        } else {
            state.selectedEmailSnapshot = null;
        }

        highlightSelectedEmail(id);

        const emailView = document.getElementById("emailView");
        if (emailView) {
            emailView.innerHTML =
                '<div class="email-loading-wrapper"><div class="loading"></div></div>';
        }

        try {
            if (!hasLoadedSentDetails(email)) {
                const detailEmail = await loadSentEmailDetail(id);
                email = mergeSentEmailDetailIntoState(detailEmail, state);
            }

            await renderSentEmailCard(email, state);
        } catch (error) {
            console.error("Не удалось загрузить детали исходящего письма", error);

            if (emailView) {
                emailView.innerHTML = `
                    <div class="email-placeholder" style="padding:20px;text-align:center;">
                        Ошибка загрузки письма
                    </div>
                `;
            }
        }
    }

    async function loadSentEmails(state) {
        const container = document.getElementById("emailsContainer");
        if (container) {
            container.innerHTML =
                '<div class="email-loading-wrapper"><div class="loading"></div></div>';
        }

        const params = new URLSearchParams({
            page: String(state.currentPage),
            per_page: String(state.perPage),
            sort: state.sortNewestFirst ? "newest" : "oldest",
        });

        if (state.currentSearchTerm.trim()) {
            params.set("search", state.currentSearchTerm.trim());
        }

        const resp = await fetch(`/api/sent?${params.toString()}`, {
            credentials: "same-origin",
        });

        if (!resp.ok) {
            throw new Error("Не удалось загрузить исходящие письма");
        }

        const data = await resp.json();

        const prevEmailsById = new Map(
            (Array.isArray(state.emails) ? state.emails : []).map((email) => [Number(email.id), email]),
        );

        state.emails = Array.isArray(data.items)
            ? data.items.map((item) => {
                  const normalized = normalizeSentItem(item);
                  const existing = prevEmailsById.get(Number(normalized.id));

                  if (!existing) {
                      return normalized;
                  }

                  return {
                        ...normalized,
                        raw_email: existing.raw_email || normalized.raw_email,
                        body_text: existing.body_text || normalized.body_text,
                        content:
                            existing.body_text ||
                            existing.raw_email ||
                            existing.content ||
                            normalized.content,
                        documents:
                            Array.isArray(existing.documents) && existing.documents.length
                                ? existing.documents
                                : normalized.documents,
                    };
              })
            : [];

        state.currentPage = Number(data.page || 1);
        state.perPage = Number(data.per_page || 100);
        state.total = Number(data.total || 0);
        state.totalPages = Number(data.total_pages || 1);

        if (
            state.selectedSourceType === "sent" &&
            state.selectedEmailId != null &&
            !state.emails.some(
                (email) => Number(email.email_id || email.id) === Number(state.selectedEmailId),
            )
        ) {
            const snapshotId = state.selectedEmailSnapshot
                ? Number(state.selectedEmailSnapshot.email_id || state.selectedEmailSnapshot.id)
                : null;

            if (snapshotId !== Number(state.selectedEmailId)) {
                const emailView = document.getElementById("emailView");
                if (emailView) {
                    emailView.innerHTML =
                        '<div class="email-placeholder">👈 Выберите письмо из списка</div>';
                }
                state.selectedEmailId = null;
            }
        }

        syncSentState(state);
    }

    function bindSearch(state) {
        const searchInput = document.getElementById("search-input");
        const clearBtn = document.getElementById("search-clear-btn");

        if (!searchInput) return;

        let searchTimer = null;

        const syncClearBtn = () => {
            if (!clearBtn) return;
            clearBtn.hidden = !searchInput.value;
        };

        searchInput.addEventListener("input", () => {
            state.currentSearchTerm = searchInput.value || "";
            syncClearBtn();

            clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                state.currentPage = 1;
                state.selectedEmailId = null;
                state.selectedSourceType = "sent";
                syncSentState(state);
                await reloadSentEmails(state);
            }, 300);
        });

        if (clearBtn) {
            clearBtn.addEventListener("click", async () => {
                searchInput.value = "";
                state.currentSearchTerm = "";
                syncClearBtn();
                state.currentPage = 1;
                state.selectedEmailId = null;
                state.selectedSourceType = "sent";
                syncSentState(state);
                await reloadSentEmails(state);
            });
        }

        syncClearBtn();
    }

    function bindSort(state) {
        const newestBtn = document.getElementById("sort-newest-btn");
        const oldestBtn = document.getElementById("sort-oldest-btn");
        const applyBtn = document.getElementById("apply-filters-btn");
        const filterToggleBtn = document.getElementById("filter-toggle-btn");
        const filterPanel = document.getElementById("filter-panel");
        const closeFilterBtn = document.getElementById("close-filter-panel");

        if (newestBtn) {
            newestBtn.addEventListener("click", () => {
                state.sortNewestFirst = true;
                state.currentPage = 1;
                newestBtn.classList.add("active");
                oldestBtn && oldestBtn.classList.remove("active");
            });
        }

        if (oldestBtn) {
            oldestBtn.addEventListener("click", () => {
                state.sortNewestFirst = false;
                state.currentPage = 1;
                oldestBtn.classList.add("active");
                newestBtn && newestBtn.classList.remove("active");
            });
        }

        if (applyBtn) {
            applyBtn.addEventListener("click", async () => {
                state.selectedEmailId = null;
                state.selectedSourceType = "sent";
                syncSentState(state);
                await reloadSentEmails(state);
                if (filterPanel) {
                    filterPanel.style.display = "none";
                }
            });
        }

        if (filterToggleBtn && filterPanel) {
            filterToggleBtn.addEventListener("click", () => {
                filterPanel.style.display =
                    filterPanel.style.display === "none" ? "block" : "none";
            });
        }

        if (closeFilterBtn && filterPanel) {
            closeFilterBtn.addEventListener("click", () => {
                filterPanel.style.display = "none";
            });
        }
    }

    async function initSentPage() {
        const initialUrlState = readSentStateFromUrl();

        const state = {
            emails: [],
            selectedEmailId: initialUrlState.selectedSourceType === "sent"
                ? initialUrlState.selectedEmailId
                : null,
            selectedSourceType: initialUrlState.selectedSourceType || "sent",
            selectedEmailSnapshot: null,
            currentSearchTerm: initialUrlState.currentSearchTerm,
            sortNewestFirst: initialUrlState.sortNewestFirst,

            currentPage: initialUrlState.currentPage,
            perPage: 100,
            total: 0,
            totalPages: 1,

            composeDraft: {},
            userSignature: "",
            _signatureLoaded: false,
        };

        const chatTabBtn = document.querySelector('[data-tab="chat"]');
        if (chatTabBtn) {
            chatTabBtn.remove();
        }

        const chatPane = document.getElementById("tab-chat");
        if (chatPane) {
            chatPane.remove();
        }

        bindSearch(state);
        bindSort(state);

        const searchInput = document.getElementById("search-input");
        if (searchInput) {
            searchInput.value = state.currentSearchTerm || "";
        }

        syncSentState(state);

        window.addEventListener("popstate", async (event) => {
            try {
                await restoreSentStateFromHistory(state, event.state);
            } catch (historyError) {
                console.error("Не удалось восстановить состояние страницы исходящих из истории", historyError);
            }
        });

        const composeDeps = {
            state,
            sendNewEmail: window.MailApi?.sendNewEmail,
            loadForwardDraft: window.MailApi?.loadForwardDraft,
            sendForwardEmail: window.MailApi?.sendForwardEmail,
        };

        state.composeDeps = composeDeps;

        const existingMailPage = window.MailPage || {};

        if (window.MailCompose?.initCompose) {
            window.MailCompose.initCompose(composeDeps);
        }

        if (typeof existingMailPage.initSignatureSettings === "function") {
            existingMailPage.initSignatureSettings();
        }

        window.MailPage = {
            ...existingMailPage,
            openForwardCompose: ({ emailId }) =>
                window.MailCompose.openForwardCompose(state.composeDeps, {
                    emailId,
                    sourceType: "sent",
                }),
        };

        try {
            await loadSentEmails(state);
            renderSentEmailList(state);
            renderSentPagination(state);

            if (state.selectedSourceType === "sent" && state.selectedEmailId != null) {
                const existingEmail = state.emails.find(
                    (email) => Number(email.id) === Number(state.selectedEmailId),
                );

                if (existingEmail) {
                    await selectSentEmail(existingEmail.id, state, { historyMode: "replace" });
                } else {
                    try {
                        const detailEmail = await loadSentEmailDetail(state.selectedEmailId);
                        const mergedEmail = mergeSentEmailDetailIntoState(detailEmail, state);

                        if (!state.emails.some((email) => Number(email.id) === Number(mergedEmail.id))) {
                            state.emails.unshift(mergedEmail);
                            renderSentEmailList(state);
                        }

                        await selectSentEmail(mergedEmail.id, state, { historyMode: "replace" });
                    } catch (detailError) {
                        console.error("Не удалось автоматически открыть исходящее письмо", detailError);
                    }
                }
            }
        } catch (error) {
            console.error(error);
            const container = document.getElementById("emailsContainer");
            if (container) {
                container.innerHTML =
                    '<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки исходящих писем</div>';
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initSentPage);
    } else {
        initSentPage();
    }
})();