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
            for (const doc of docs) {
                await downloadBlob(
                    `/api/documents/${doc.id}/download`,
                    doc.document_name,
                );
            }
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

    async function downloadAvailableResultDocuments(docs) {
        if (!docs.length) {
            alert("Нет файлов для скачивания");
            return;
        }

        for (const doc of docs) {
            await downloadBlob(
                `/api/documents/${doc.id}/result-download?variant=${encodeURIComponent(doc.variant || "main")}`,
                doc.filename || `result-doc-${doc.id}`,
            );
        }
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

    window.MailApi = {
        downloadBlob,
        downloadEmailAttachments,
        loadAvailableResultDocuments,
        downloadAvailableResultDocuments,
        loadEmailsFromApi,
    };
})();