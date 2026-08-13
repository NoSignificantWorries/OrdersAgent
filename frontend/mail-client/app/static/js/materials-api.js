(function () {
    async function getErrorMessage(response, fallbackMessage) {
        try {
            const data = await response.json();

            if (data?.detail && typeof data.detail === "string") {
                return data.detail;
            }
        } catch (_) {}

        return fallbackMessage;
    }

    async function loadMappings(options = {}) {
        const {
            cursor = null,
            limit = 50,
            search = "",
            signal = undefined,
        } = options;

        const url = new URL("/api/mappings", window.location.origin);
        url.searchParams.set("limit", String(limit));

        if (cursor) {
            url.searchParams.set("cursor", String(cursor));
        }

        if (String(search || "").trim()) {
            url.searchParams.set("search", String(search).trim());
        }

        const response = await fetch(url.toString(), {
            method: "GET",
            headers: {
                Accept: "application/json",
            },
            credentials: "same-origin",
            cache: "no-store",
            signal,
        });

        if (!response.ok) {
            throw new Error(
                await getErrorMessage(
                    response,
                    `Не удалось загрузить материалы (${response.status})`,
                ),
            );
        }

        return await response.json();
    }

    async function createMapping(payload) {
        const response = await fetch("/api/mappings", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            credentials: "same-origin",
            cache: "no-store",
            body: JSON.stringify({
                source: String(payload?.source || "").trim(),
                target: String(payload?.target || "").trim(),
                article: String(payload?.article || "").trim(),
            }),
        });

        if (!response.ok) {
            throw new Error(
                await getErrorMessage(response, "Не удалось добавить материал"),
            );
        }

        return await response.json();
    }

    async function updateMapping(payload) {
        const response = await fetch("/api/mappings", {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            credentials: "same-origin",
            cache: "no-store",
            body: JSON.stringify({
                source: String(payload?.source || "").trim(),
                target: String(payload?.target || "").trim(),
                article: String(payload?.article || "").trim(),
            }),
        });

        if (!response.ok) {
            throw new Error(
                await getErrorMessage(response, "Не удалось сохранить материал"),
            );
        }

        return await response.json();
    }

    window.MaterialsApi = {
        loadMappings,
        createMapping,
        updateMapping,
    };
})();