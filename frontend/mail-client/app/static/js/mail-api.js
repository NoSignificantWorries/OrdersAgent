(function () {
    const {
        mapTaskStatusToUiStatus,
    } = window.MailFormatters;

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

        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = filename || "file";
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

            await downloadBlob(
                `/api/emails/${email.id}/attachments/download-all`,
                `email-${email.id}-attachments.zip`,
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

    async function loadEmailsFromApi(showLoadingState = true, normalizeApiItem) {
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
            const url = cfg.apiUrl || "/api/queue";

            const resp = await fetch(url, {
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
                return { ok: false, emails: [] };
            }

            if (!resp.ok) {
                if (countSpan) countSpan.textContent = "Ошибка";
                if (listEl) {
                    listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
                }
                if (viewEl) {
                    viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
                }
                return { ok: false, emails: [] };
            }

            const data = await resp.json();
            const items = Array.isArray(data.items) ? data.items : [];
            const emails = items.map((item, idx) => normalizeApiItem(item, idx));

            if (countSpan) countSpan.textContent = `${emails.length} писем`;

            return { ok: true, emails };
        } catch (e) {
            console.error("Ошибка загрузки писем:", e);

            const listEl = document.getElementById("emailsContainer");
            const viewEl = document.getElementById("emailView");
            const countSpan = document.getElementById("email-count-display");

            if (countSpan) countSpan.textContent = "Ошибка";
            if (listEl) {
                listEl.innerHTML = `<div class="email-placeholder" style="padding:20px;text-align:center;">Ошибка загрузки писем</div>`;
            }
            if (viewEl) {
                viewEl.innerHTML = `<div class="email-placeholder">Ошибка загрузки писем</div>`;
            }

            return { ok: false, emails: [] };
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

    async function loadForwardDraft(emailId) {
        const resp = await fetch(`/api/emails/${emailId}/forward-draft`, {
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

    window.MailApi = {
        downloadBlob,
        downloadEmailAttachments,
        loadAvailableResultDocuments,
        downloadAvailableResultDocuments,
        loadEmailsFromApi,
        sendNewEmail,
        loadForwardDraft,
        sendForwardEmail,
        getMySignature,
        updateMySignature,
    };
})();