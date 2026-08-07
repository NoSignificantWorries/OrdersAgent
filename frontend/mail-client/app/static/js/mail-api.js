(function () {
    const {
        mapTaskStatusToUiStatus,
    } = window.MailFormatters;

    function pickSafeEmailDate(item) {
        const primary =
            item?.date ??
            item?.email_date ??
            item?.emaildate ??
            "";

        const fallback =
            item?.created_at ??
            item?.createdat ??
            "";

        const rawPrimary = String(primary || "").trim();
        if (!rawPrimary || rawPrimary.startsWith("0001-01-01")) {
            return fallback || "";
        }

        return rawPrimary;
    }

    function getFilenameFromContentDisposition(headerValue) {
        if (!headerValue) return "";

        const utf8Match = headerValue.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
        if (utf8Match && utf8Match[1]) {
            try {
                return decodeURIComponent(utf8Match[1]);
            } catch (_) {}
        }

        const asciiMatch = headerValue.match(/filename\s*=\s*"([^"]+)"/i)
            || headerValue.match(/filename\s*=\s*([^;]+)/i);

        if (asciiMatch && asciiMatch[1]) {
            return asciiMatch[1].trim().replace(/^"|"$/g, "");
        }

        return "";
    }

    async function downloadBlob(url, filename) {
        const resp = await fetch(url, {
            method: "GET",
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let message = "Ошибка скачивания файла";
            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {}

            throw new Error(message);
        }

        const blob = await resp.blob();
        const objectUrl = URL.createObjectURL(blob);

        const contentDisposition = resp.headers.get("Content-Disposition") || "";
        const serverFilename = getFilenameFromContentDisposition(contentDisposition);
        const finalFilename = serverFilename || filename || "file";

        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = finalFilename;
        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    }

    async function downloadEmailAttachments(email, getDisplayDocuments) {
        const docs = getDisplayDocuments(email).filter((doc) => doc && doc.id);
        if (!docs.length) {
            alert("У письма нет вложений для скачивания");
            return;
        }

        try {
            if (docs.length === 1) {
                const doc = docs[0];
                await downloadBlob(
                    `/api/documents/${doc.id}/download`,
                    doc.document_name || `document-${doc.id}`,
                );
                return;
            }

            const emailId = Number(email.email_id || email.emailid || email.id);

            if (!Number.isFinite(emailId) || emailId <= 0) {
                throw new Error("Не удалось определить ID письма");
            }

            await downloadBlob(
                `/api/emails/${emailId}/attachments/download-all`,
                `email-${emailId}-attachments.zip`,
            );
        } catch (e) {
            console.error(e);
            alert(e.message || "Ошибка скачивания вложений");
        }
    }

    async function loadAvailableResultDocuments(taskId) {
        const resp = await fetch(`/api/tasks/${taskId}/result-documents`, {
            method: "GET",
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let message = "Не удалось получить список результирующих файлов";
            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {}

            throw new Error(message);
        }

        const data = await resp.json();
        return data.documents || [];
    }

    async function downloadAvailableResultDocuments(taskId, docs) {
        if (!docs.length) {
            alert("Нет файлов для скачивания");
            return;
        }

        if (docs.length === 1) {
            const doc = docs[0];
            await downloadBlob(
                `/api/documents/${doc.id}/result-download?variant=${encodeURIComponent(doc.variant || "main")}`,
                doc.filename || `result-doc-${doc.id}`,
            );
            return;
        }

        await downloadBlob(
            `/api/tasks/${taskId}/result-documents/download-all`,
            `task-${taskId}-results.zip`,
        );
    }

    async function loadEmailsFromApi(options = {}) {
        const {
            showLoadingState = true,
            normalizeApiItem = (item) => item,
            page = 1,
            perPage = 50,
            extraParams = {},
        } = options || {};

        const listEl = document.getElementById("emailsContainer");
        const viewEl = document.getElementById("emailView");
        const countSpan = document.getElementById("email-count-display");

        try {
            if (showLoadingState) {
                if (countSpan) countSpan.textContent = "Загрузка...";
                if (listEl) {
                    listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Загрузка писем...</div>`;
                }
            }

            const cfg = window.__MAIL_PAGE_CONFIG__ || {};
            const baseUrl = cfg.apiUrl || "/api/queue";

            const url = new URL(baseUrl, window.location.origin);
            url.searchParams.set("page", String(page));
            url.searchParams.set("per_page", String(perPage));

            Object.entries(extraParams || {}).forEach(([key, value]) => {
                if (value === undefined || value === null || value === "" || value === "all") {
                    return;
                }
                url.searchParams.set(key, String(value));
            });

            const resp = await fetch(url.toString(), {
                method: "GET",
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });

            if (resp.status === 401) {
                if (countSpan) countSpan.textContent = "Не авторизован";
                if (listEl) {
                    listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Нужно войти заново</div>`;
                }
                if (viewEl) {
                    viewEl.innerHTML = `<div class="email-placeholder">Нужно войти заново</div>`;
                }

                return {
                    ok: false,
                    emails: [],
                    pagination: {
                        page: 1,
                        perPage,
                        total: 0,
                        totalPages: 1,
                    },
                };
            }

            if (!resp.ok) {
                if (countSpan) countSpan.textContent = "Ошибка";
                if (listEl) {
                    listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
                }
                if (viewEl) {
                    viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
                }

                return {
                    ok: false,
                    emails: [],
                    pagination: {
                        page: 1,
                        perPage,
                        total: 0,
                        totalPages: 1,
                    },
                };
            }

            const data = await resp.json();
            const items = Array.isArray(data.items) ? data.items : [];
            const normalize =
                typeof normalizeApiItem === "function"
                    ? normalizeApiItem
                    : (item) => item;
            const emails = items.map((item, idx) => {
                const patchedItem = {
                    ...item,
                    date: pickSafeEmailDate(item),
                    email_date: pickSafeEmailDate(item),
                    emaildate: pickSafeEmailDate(item),
                };
                return normalize(patchedItem, idx);
            });

            const total = Number(data.total ?? emails.length);
            const currentPage = Number(data.page ?? page);
            const currentPerPage = Number(data.per_page ?? perPage);
            const totalPages = Number(
                data.total_pages ?? Math.max(1, Math.ceil(total / currentPerPage))
            );

            if (countSpan) {
                countSpan.textContent = `${total} писем`;
            }

            return {
                ok: true,
                emails,
                pagination: {
                    page: currentPage,
                    perPage: currentPerPage,
                    total,
                    totalPages,
                },
            };
        } catch (e) {
            console.error("Ошибка загрузки писем:", e);

            if (countSpan) countSpan.textContent = "Ошибка";
            if (listEl) {
                listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
            }
            if (viewEl) {
                viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
            }

            return {
                ok: false,
                emails: [],
                pagination: {
                    page: 1,
                    perPage,
                    total: 0,
                    totalPages: 1,
                },
            };
        }
    }

    async function sendNewEmail(formData) {
        const resp = await fetch("/api/emails/send", {
            method: "POST",
            credentials: "same-origin",
            body: formData,
        });

        if (!resp.ok) {
            let message = "Не удалось отправить письмо";
            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {}

            throw new Error(message);
        }

        window.MailPage?.showMailToast?.("Письмо отправлено");

        return resp;
    }

    async function loadForwardDraft(emailId, options = {}) {
        const sourceType = options?.sourceType === "sent" ? "sent" : "inbox";

        const url = new URL(`/api/emails/${emailId}/forward-draft`, window.location.origin);
        url.search = new URLSearchParams({
            source_type: sourceType,
        }).toString();

        const resp = await fetch(url.toString(), {
            method: "GET",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let message = "Не удалось получить черновик пересылки";

            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {
                try {
                    const text = await resp.text();
                    if (text?.trim()) {
                        message = text.trim();
                    }
                } catch (_) {}
            }

            throw new Error(message);
        }

        return await resp.json();
    }

    async function loadReplyDraft(emailId, options = {}) {
        const sourceType = options?.sourceType === "sent" ? "sent" : "inbox";

        const url = new URL(`/api/emails/${emailId}/reply-draft`, window.location.origin);
        url.search = new URLSearchParams({
            source_type: sourceType,
        }).toString();

        const resp = await fetch(url.toString(), {
            method: "GET",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let message = "Не удалось получить черновик ответа";

            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {
                try {
                    const text = await resp.text();
                    if (text?.trim()) {
                        message = text.trim();
                    }
                } catch (_) {}
            }

            throw new Error(message);
        }

        return await resp.json();
    }

    async function sendForwardEmail(emailId, formData) {
        const resp = await fetch(`/api/emails/${emailId}/forward`, {
            method: "POST",
            credentials: "same-origin",
            body: formData,
        });

        if (!resp.ok) {
            let message = "Не удалось переслать письмо";

            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {
                try {
                    const text = await resp.text();
                    if (text?.trim()) {
                        message = text.trim();
                    }
                } catch (_) {}
            }

            throw new Error(message);
        }

        window.MailPage?.showMailToast?.("Письмо переслано");

        return resp;
    }

    async function getMySignature() {
        const response = await fetch("/api/me/signature", {
            method: "GET",
            headers: {
                Accept: "application/json",
            },
            credentials: "same-origin",
        });

        if (!response.ok) {
            let detail = "Не удалось загрузить подпись";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string" && data.detail.trim()) {
                    detail = data.detail.trim();
                }
            } catch (_) {}
            throw new Error(detail);
        }

        const data = await response.json();
        return String(data?.signature || "");
    }

    async function updateMySignature(signature) {
        const response = await fetch("/api/me/signature", {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            credentials: "same-origin",
            body: JSON.stringify({
                signature: String(signature || ""),
            }),
        });

        if (!response.ok) {
            let detail = "Не удалось сохранить подпись";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string" && data.detail.trim()) {
                    detail = data.detail.trim();
                }
            } catch (_) {}
            throw new Error(detail);
        }

        return await response.json();
    }

    async function getEmailComment(emailId) {
        const resp = await fetch(`/api/emails/${emailId}/comment`, {
            method: "GET",
            headers: {
                Accept: "application/json",
            },
            credentials: "same-origin",
        });

        if (!resp.ok) {
            let message = "Не удалось загрузить комментарий";
            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {}

            throw new Error(message);
        }

        return await resp.json();
    }

    async function updateEmailComment(emailId, commentText) {
        const resp = await fetch(`/api/emails/${emailId}/comment`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            credentials: "same-origin",
            body: JSON.stringify({
                comment_text: String(commentText || ""),
            }),
        });

        if (!resp.ok) {
            let message = "Не удалось сохранить комментарий";
            try {
                const data = await resp.json();
                if (data?.detail) {
                    message = data.detail;
                }
            } catch (_) {}

            throw new Error(message);
        }

        return await resp.json();
    }

    window.MailApi = {
        downloadBlob,
        downloadEmailAttachments,
        loadAvailableResultDocuments,
        downloadAvailableResultDocuments,
        loadEmailsFromApi,
        sendNewEmail,
        loadForwardDraft,
        loadReplyDraft,
        sendForwardEmail,
        getMySignature,
        updateMySignature,
        getEmailComment,
        updateEmailComment,
    };
})();