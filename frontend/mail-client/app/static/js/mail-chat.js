(function () {
    console.error("MAIL-CHAT NEW FILE LOADED");

    // function extractMaterialNames(value) {
    //     if (!value) return [];

    //     if (Array.isArray(value)) {
    //         return value.flatMap((item) => {
    //             if (typeof item === "string") {
    //                 const s = item.trim();
    //                 return s ? [s] : [];
    //             }

    //             if (item && typeof item === "object" && !Array.isArray(item)) {
    //                 return Object.keys(item)
    //                     .map((k) => String(k).trim())
    //                     .filter(Boolean);
    //             }

    //             return [];
    //         });
    //     }

    //     if (value && typeof value === "object") {
    //         return Object.keys(value)
    //             .map((k) => String(k).trim())
    //             .filter(Boolean);
    //     }

    //     return [];
    // }

    // function extractMaterialsFromOutput(output) {
    //     if (!output || typeof output !== "object") return ["output_data"];

    //     if (Array.isArray(output)) {
    //         return extractMaterialNames(output);
    //     }

    //     const candidates = [
    //         output.queries,
    //         output.requests,
    //         output.materials,
    //         output.material_queries,
    //         output.output_data,
    //         output.data,
    //         output.items,
    //         output.result,
    //     ];

    //     for (const value of candidates) {
    //         const names = extractMaterialNames(value);
    //         if (names.length > 0) return names;
    //     }

    //     for (const value of Object.values(output)) {
    //         const names = extractMaterialNames(value);
    //         if (names.length > 0) return names;
    //     }

    //     return [];
    // }

    function extractMaterialsFromOutput(output) {
        console.log("[MailChat] extractMaterialsFromOutput: raw output =", output);
        console.log(
            "[MailChat] extractMaterialsFromOutput: keys =",
            output && typeof output === "object" && !Array.isArray(output)
                ? Object.keys(output)
                : null,
        );

        if (!output || typeof output !== "object" || Array.isArray(output)) {
            return [];
        }

        return Object.keys(output)
            .map((k) => String(k).trim())
            .filter(Boolean);
    }

    // function buildChatItemsFromOutput(output, emailId, chatStorage) {
    //     const safeChatStorage =
    //         chatStorage instanceof Map ? chatStorage : new Map();

    //     const materials = extractMaterialsFromOutput(output);

    //     const manualDecision =
    //         output &&
    //         !Array.isArray(output) &&
    //         output.manual_decision &&
    //         typeof output.manual_decision === "object" &&
    //         !Array.isArray(output.manual_decision)
    //             ? output.manual_decision
    //             : {};

    //     const chatItems = materials.map((material) => {
    //         const saved = manualDecision[material];
    //         return {
    //             material,
    //             answer: Array.isArray(saved) ? String(saved[0] ?? "") : "",
    //             blacklist: Array.isArray(saved) ? Boolean(saved[1]) : false,
    //         };
    //     });

    //     const cached = safeChatStorage.get(emailId);
    //     if (Array.isArray(cached) && cached.length > 0) {
    //         return chatItems.map((item) => {
    //             const fromCache = cached.find((x) => x.material === item.material);
    //             return fromCache
    //                 ? {
    //                       ...item,
    //                       answer: fromCache.answer,
    //                       blacklist: fromCache.blacklist,
    //                   }
    //                 : item;
    //         });
    //     }

    //     return chatItems;
    // }

    function buildChatItemsFromOutput(output, emailId, chatStorage) {
        console.log("[MailChat] buildChatItemsFromOutput: emailId =", emailId);
        console.log("[MailChat] buildChatItemsFromOutput: output =", output);

        const safeChatStorage =
            chatStorage instanceof Map ? chatStorage : new Map();

        const materials = extractMaterialsFromOutput(output);
        console.log("[MailChat] buildChatItemsFromOutput: materials =", materials);

        const source = output && typeof output === "object" && !Array.isArray(output)
            ? output
            : {};

        const chatItems = materials.map((material) => {
            const saved = source[material];
            const row = saved && typeof saved === "object" && !Array.isArray(saved)
                ? saved
                : {};

            console.log("[MailChat] material row:", {
                material,
                saved,
                normalized: {
                    target: row.target == null ? "" : String(row.target),
                    article: row.article == null ? "" : String(row.article),
                    blacklist: Boolean(row["black-list"]),
                },
            });

            return {
                material,
                target: row.target == null ? "" : String(row.target),
                article: row.article == null ? "" : String(row.article),
                blacklist: Boolean(row["black-list"]),
            };
        });

        console.log("[MailChat] buildChatItemsFromOutput: chatItems =", chatItems);

        const cached = safeChatStorage.get(emailId);
        console.log("[MailChat] buildChatItemsFromOutput: cached =", cached);

        if (Array.isArray(cached) && cached.length > 0) {
            const merged = chatItems.map((item) => {
                const fromCache = cached.find((x) => x.material === item.material);
                return fromCache
                    ? {
                        ...item,
                        target: fromCache.target ?? item.target,
                        article: fromCache.article ?? item.article,
                        blacklist: Boolean(fromCache.blacklist),
                    }
                    : item;
            });

            console.log("[MailChat] buildChatItemsFromOutput: merged chatItems =", merged);
            return merged;
        }

        return chatItems;
    }

    function isEditingMaterialInput() {
        const active = document.activeElement;
        return !!(
            active &&
            active.classList &&
            active.classList &&
            (
                active.classList.contains("target-input") ||
                active.classList.contains("article-input")
            )
        );
    }

    function isChatTabActive() {
        const chatTab = document.getElementById("tab-chat");
        return !!(chatTab && chatTab.classList.contains("active"));
    }

    function isMaterialInputProtected(state) {
        return (
            isChatTabActive() &&
            (isEditingMaterialInput() || state.isMaterialInputComposing)
        );
    }

    function bindMaterialInputEvents({ input, item, email, deps, field }) {
        if (!input) return;

        const { state, refreshEmailsSilently } = deps;

        input.addEventListener("compositionstart", () => {
            state.isMaterialInputComposing = true;
        });

        input.addEventListener("compositionend", (e) => {
            state.isMaterialInputComposing = false;
            item[field] = e.target.value;
            state.chatStorage.set(email.id, email.chatItems);

            if (state.pendingSilentRefresh && !isEditingMaterialInput()) {
                state.pendingSilentRefresh = false;
                refreshEmailsSilently();
            }
        });

        input.addEventListener("blur", (e) => {
            state.isMaterialInputComposing = false;
            item[field] = e.target.value;
            state.chatStorage.set(email.id, email.chatItems);

            setTimeout(() => {
                if (!isEditingMaterialInput() && state.pendingSilentRefresh) {
                    state.pendingSilentRefresh = false;
                    refreshEmailsSilently();
                }
            }, 0);
        });

        input.addEventListener("input", (e) => {
            item[field] = e.target.value;
            state.chatStorage.set(email.id, email.chatItems);

            if (e.isComposing) {
                state.isMaterialInputComposing = true;
            }
        });
    }

    async function renderChatForEmail(email, deps) {
        const {
            state,
            escapeHtml,
            loadAvailableResultDocuments,
            downloadAvailableResultDocuments,
        } = deps;

        console.log("[MailChat] renderChatForEmail: email =", email);
        console.log("[MailChat] renderChatForEmail: email.chatItems =", email?.chatItems);

        const container = document.getElementById("chat-rows-container");
        const submitContainer = document.querySelector(".chat-submit");

        if (!container) return;
        if (submitContainer) submitContainer.style.display = "none";

        if (!email) {
            container.innerHTML =
                '<div class="chat-placeholder">👈 Выберите письмо из списка</div>';
            return;
        }

        const taskStatus = String(
            email.task_status || email.taskstatus || email.task?.status || "",
        ).toLowerCase();

        if (taskStatus === "completed") {
            if (!email?.task?.id) {
                container.innerHTML =
                    '<div class="chat-placeholder">Нет данных по задаче</div>';
                return;
            }

            container.innerHTML =
                '<div class="chat-placeholder">Загрузка результирующих файлов...</div>';

            loadAvailableResultDocuments(email.task.id)
                .then((docs) => {
                    if (!docs.length) {
                        container.innerHTML =
                            '<div class="chat-placeholder">Результирующие файлы отсутствуют</div>';
                        return;
                    }

                    const filesHtml = docs
                        .map((doc) => {
                            const filename = doc?.filename || `document-${doc.id}`;
                            return `<li>${escapeHtml(String(filename))}</li>`;
                        })
                        .join("");

                    container.innerHTML = `
                        <div class="email-attachments">
                            <strong>Результирующие файлы:</strong>
                            <ul>${filesHtml}</ul>
                            <button class="save-all-attachments-btn" data-email-id="${email.id}">
                                Скачать
                            </button>
                        </div>
                    `;

                    const downloadBtn = container.querySelector(".save-all-attachments-btn");
                    if (downloadBtn) {
                        downloadBtn.addEventListener("click", async (e) => {
                            e.stopPropagation();
                            try {
                                await downloadAvailableResultDocuments(docs);
                            } catch (err) {
                                console.error(err);
                                alert(err.message || "Ошибка скачивания");
                            }
                        });
                    }
                })
                .catch((err) => {
                    console.error(err);
                    container.innerHTML = `
                        <div class="chat-placeholder">
                            ${escapeHtml(err.message || "Ошибка загрузки файлов")}
                        </div>
                    `;
                });

            return;
        }

        if (taskStatus !== "materials_review") {
            container.innerHTML =
                '<div class="chat-placeholder">Чат доступен только для задач на проверке материалов</div>';
            return;
        }

        if (!email.chatItems || email.chatItems.length === 0) {
            container.innerHTML =
                '<div class="chat-placeholder">Нет данных output_data для формирования материалов</div>';
            return;
        }

        if (submitContainer) submitContainer.style.display = "block";

        let html = "";
        email.chatItems.forEach((item, idx) => {
            html += `
                <div class="chat-row" data-row-idx="${idx}">
                    <div class="chat-row-top">
                        <div class="material-name">${escapeHtml(item.material)}</div>
                        <label class="blacklist-label">
                            <input
                                type="checkbox"
                                class="blacklist-checkbox"
                                ${item.blacklist ? "checked" : ""}
                            >
                            Черный список
                        </label>
                    </div>
                    <div class="chat-row-bottom chat-row-bottom-two-fields">
                        <input
                            type="text"
                            class="article-input"
                            value="${escapeHtml(item.article || "")}"
                            placeholder="Введите артикул"
                        >
                        <input
                            type="text"
                            class="target-input"
                            value="${escapeHtml(item.target || "")}"
                            placeholder="Введите полуфабрикат"
                        >
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;

        email.chatItems.forEach((item, idx) => {
        const row = container.querySelector(`.chat-row[data-row-idx="${idx}"]`);
        if (!row) return;

        const articleInput = row.querySelector(".article-input");
        const targetInput = row.querySelector(".target-input");
        const chk = row.querySelector(".blacklist-checkbox");

        if (articleInput) {
            bindMaterialInputEvents({
                input: articleInput,
                item,
                email,
                deps,
                field: "article",
            });
        }

        if (targetInput) {
            bindMaterialInputEvents({
                input: targetInput,
                item,
                email,
                deps,
                field: "target",
            });
        }

        if (chk) {
            chk.addEventListener("change", (e) => {
                item.blacklist = e.target.checked;
                state.chatStorage.set(email.id, email.chatItems);
            });
        }
    });
    }

    async function sendChatData(deps) {
        const {
            state,
            loadEmailsFromApi,
            renderEmailList,
            renderEmailCard,
            highlightSelectedEmail,
            renderChatForEmail,
        } = deps;

        const email = state.emails.find((e) => e.id === state.selectedEmailId);

        if (!email) {
            alert("Письмо не выбрано");
            return;
        }

        if (!email.task?.id) {
            alert("У письма нет задачи");
            return;
        }

        if (
            String(email.task_status || email.taskstatus || "").toLowerCase() !==
            "materials_review"
        ) {
            alert("Отправка доступна только для статуса materials_review");
            return;
        }

        if (!email.chatItems || email.chatItems.length === 0) {
            alert("Нет данных для отправки");
            return;
        }

        const manualDecision = {};
        email.chatItems.forEach((item) => {
            manualDecision[item.material] = {
                target: String(item.target || "").trim() || null,
                article: String(item.article || "").trim() || null,
                "black-list": Boolean(item.blacklist),
            };
        });

        try {
            const resp = await fetch(`/api/queue/${email.task.id}/manual-decision`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    manual_decision: manualDecision,
                }),
            });

            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                let message = "Ошибка отправки";

                if (typeof data?.detail === "string") {
                    message = data.detail;
                } else if (Array.isArray(data?.detail)) {
                    message = data.detail
                        .map((x) => x?.msg || JSON.stringify(x))
                        .join("; ");
                } else if (data?.detail && typeof data.detail === "object") {
                    message = JSON.stringify(data.detail);
                }

                throw new Error(message);
            }

            const savedEmailId = email.id;
            state.chatStorage.delete(email.id);

            await loadEmailsFromApi(false);
            renderEmailList();

            const freshEmail = state.emails.find((e) => e.id === savedEmailId);
            if (freshEmail) {
                state.selectedEmailId = freshEmail.id;
                highlightSelectedEmail(freshEmail.id);

                const chatTab = document.getElementById("tab-chat");
                if (chatTab && chatTab.classList.contains("active")) {
                    renderChatForEmail(freshEmail, deps);
                } else {
                    renderEmailCard(freshEmail);
                }
            }
        } catch (e) {
            console.error(e);
            alert(e.message || "Ошибка");
        }
    }

    window.MailChat = {
        extractMaterialsFromOutput,
        buildChatItemsFromOutput,
        isEditingMaterialInput,
        isChatTabActive,
        isMaterialInputProtected,
        bindMaterialInputEvents,
        renderChatForEmail,
        sendChatData,
    };
})();