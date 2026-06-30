(function () {
    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatDate(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleDateString("ru-RU");
    }

    function formatTimeOnly(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleTimeString("ru-RU", {
            hour: "2-digit",
            minute: "2-digit",
        });
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
            id: Number(item.emailid || item.id),
            email_id: Number(item.emailid || item.id),
            subject,
            sender,
            mailbox: recipient,
            recipient,
            to_header: item.toheader || "",
            cc_header: item.ccheader || "",
            bcc_header: item.bccheader || "",
            content: item.bodytext || item.rawemail || "",
            body_text: item.bodytext || "",
            raw_email: item.rawemail || "",
            date,
            read: true,
            archived: false,
            status: null,
            model_decision: null,
            predicted_class: null,
            prob_1: null,
            message_id: item.messageid || "",
            in_reply_to: item.inreplyto || "",
            references: item.references || "",
            documents: normalizeDocuments(item.documents),
            task: null,
            source_type: "sent",
        };
    }

    function renderSentEmailList(state) {
        const container = document.getElementById("emailsContainer");
        if (!container) return;

        let filtered = [...state.emails];

        if (state.currentSearchTerm.trim() !== "") {
            const term = state.currentSearchTerm.toLowerCase();
            filtered = filtered.filter((email) =>
                String(email.subject || "").toLowerCase().includes(term) ||
                String(email.sender || "").toLowerCase().includes(term) ||
                String(email.recipient || "").toLowerCase().includes(term) ||
                String(email.content || "").toLowerCase().includes(term)
            );
        }

        filtered.sort((a, b) => {
            const dateA = new Date(a.date || 0);
            const dateB = new Date(b.date || 0);
            return state.sortNewestFirst ? dateB - dateA : dateA - dateB;
        });

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
            el.addEventListener("click", () => selectSentEmail(Number(el.dataset.id), state));
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

    function renderSentEmailCard(email, state) {
        const emailView = document.getElementById("emailView");
        if (!emailView) return;

        const docs = Array.isArray(email.documents) ? email.documents : [];

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

        console.log("SENT BODY RAW =", JSON.stringify(email.body_text || email.content || ""));

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
                        data-email-id="${email.email_id}"
                    >
                        ${docs.length === 1 ? "Скачать" : "Скачать все"}
                    </button>
                </div>
            `
            : "";

            const actionsHtml = `
                <div class="reply-block">
                    <div class="reply-toolbar">
                        <button
                            type="button"
                            id="forward-toggle-btn"
                            class="reply-btn reply-btn-primary"
                        >
                            Переслать
                        </button>
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

        const forwardToggleBtn = emailView.querySelector("#forward-toggle-btn");
            if (forwardToggleBtn) {
                forwardToggleBtn.addEventListener("click", async () => {
                    forwardToggleBtn.disabled = true;

                    try {
                        const realEmailId = email.email_id || email.id;

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

    function selectSentEmail(id, state) {
        state.selectedEmailId = id;

        const email = state.emails.find((e) => e.id === id);
        if (!email) return;

        highlightSelectedEmail(id);
        renderSentEmailCard(email, state);
    }

    async function loadSentEmails(state) {
        const container = document.getElementById("emailsContainer");
        if (container) {
            container.innerHTML =
                '<div class="email-loading-wrapper"><div class="loading"></div></div>';
        }

        const resp = await fetch("/api/sent", {
            credentials: "same-origin",
        });

        if (!resp.ok) {
            throw new Error("Не удалось загрузить исходящие письма");
        }

        const data = await resp.json();
        console.log("SENT API DATA =", data);

        state.emails = Array.isArray(data.items) ? data.items.map(normalizeSentItem) : [];
        console.log("SENT NORMALIZED EMAILS =", state.emails);
    }

    function bindSearch(state) {
        const searchInput = document.getElementById("search-input");
        const clearBtn = document.getElementById("search-clear-btn");

        if (!searchInput) return;

        const syncClearBtn = () => {
            if (!clearBtn) return;
            clearBtn.hidden = !searchInput.value;
        };

        searchInput.addEventListener("input", () => {
            state.currentSearchTerm = searchInput.value || "";
            syncClearBtn();
            renderSentEmailList(state);
        });

        if (clearBtn) {
            clearBtn.addEventListener("click", () => {
                searchInput.value = "";
                state.currentSearchTerm = "";
                syncClearBtn();
                renderSentEmailList(state);
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
                newestBtn.classList.add("active");
                oldestBtn && oldestBtn.classList.remove("active");
            });
        }

        if (oldestBtn) {
            oldestBtn.addEventListener("click", () => {
                state.sortNewestFirst = false;
                oldestBtn.classList.add("active");
                newestBtn && newestBtn.classList.remove("active");
            });
        }

        if (applyBtn) {
            applyBtn.addEventListener("click", () => {
                renderSentEmailList(state);
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
        const state = {
            emails: [],
            selectedEmailId: null,
            currentSearchTerm: "",
            sortNewestFirst: true,

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

        const composeDeps = {
            state,
            sendNewEmail: window.MailApi?.sendNewEmail,
            loadForwardDraft: window.MailApi?.loadForwardDraft,
            sendForwardEmail: window.MailApi?.sendForwardEmail,
        };

        state.composeDeps = composeDeps;

        if (window.MailCompose?.initCompose) {
            window.MailCompose.initCompose(composeDeps);
        }

        window.MailPage = window.MailPage || {};
        window.MailPage.openForwardCompose = ({ emailId }) =>
            window.MailCompose.openForwardCompose(state.composeDeps, {
                emailId,
                sourceType: "sent",
            });

        try {
            await loadSentEmails(state);
            renderSentEmailList(state);
        } catch (error) {
            console.error(error);
            const container = document.getElementById("emailsContainer");
            if (container) {
                container.innerHTML =
                    '<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки исходящих писем</div>';
            }
        }
    }

    document.addEventListener("DOMContentLoaded", initSentPage);
})();