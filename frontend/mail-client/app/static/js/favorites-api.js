(function () {
    const API_URL = "/api/favorite-senders";

    async function getErrorMessage(response, fallbackMessage) {
        try {
            const data = await response.json();

            if (typeof data?.detail === "string" && data.detail.trim()) {
                return data.detail;
            }

            // Ошибки валидации FastAPI приходят массивом в detail.
            if (Array.isArray(data?.detail)) {
                const messages = data.detail
                    .map((error) => {
                        const field = Array.isArray(error?.loc)
                            ? error.loc
                                .filter((part) => part !== "body")
                                .join(".")
                            : "";

                        const message = String(error?.msg || "").trim();

                        if (!message) return "";
                        return field ? `${field}: ${message}` : message;
                    })
                    .filter(Boolean);

                if (messages.length) {
                    return messages.join("\n");
                }
            }
        } catch (_) {}

        return fallbackMessage;
    }

    async function loadFavoriteSenders(options = {}) {
        const {
            cursor = null,
            limit = 50,
            search = "",
            signal = undefined,
        } = options;

        const url = new URL(API_URL, window.location.origin);
        url.searchParams.set("limit", String(limit));

        if (cursor !== null && cursor !== undefined) {
            url.searchParams.set("cursor", String(cursor));
        }

        const normalizedSearch = String(search || "").trim();

        if (normalizedSearch) {
            url.searchParams.set("search", normalizedSearch);
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
                    `Не удалось загрузить избранные почты (${response.status})`,
                ),
            );
        }

        return await response.json();
    }

    async function createFavoriteSender(payload) {
        const response = await fetch(API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            credentials: "same-origin",
            cache: "no-store",
            body: JSON.stringify({
                email: String(payload?.email || "").trim(),
                comment: String(payload?.comment || "").trim() || null,
            }),
        });

        if (!response.ok) {
            throw new Error(
                await getErrorMessage(
                    response,
                    "Не удалось добавить адрес в избранное",
                ),
            );
        }

        return await response.json();
    }

    async function updateFavoriteSender(senderId, payload) {
        const changes = {};

        // Неотправленное поле должно остаться без изменений.
        if (Object.prototype.hasOwnProperty.call(payload || {}, "email")) {
            changes.email = payload.email === null
                ? null
                : String(payload.email || "").trim();
        }

        if (Object.prototype.hasOwnProperty.call(payload || {}, "comment")) {
            changes.comment = String(payload.comment || "").trim() || null;
        }

        const response = await fetch(
            `${API_URL}/${encodeURIComponent(String(senderId))}`,
            {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                },
                credentials: "same-origin",
                cache: "no-store",
                body: JSON.stringify(changes),
            },
        );

        if (!response.ok) {
            throw new Error(
                await getErrorMessage(
                    response,
                    "Не удалось сохранить избранный адрес",
                ),
            );
        }

        return await response.json();
    }

    async function deleteFavoriteSender(senderId) {
        const response = await fetch(
            `${API_URL}/${encodeURIComponent(String(senderId))}`,
            {
                method: "DELETE",
                headers: {
                    Accept: "application/json",
                },
                credentials: "same-origin",
                cache: "no-store",
            },
        );

        if (!response.ok) {
            throw new Error(
                await getErrorMessage(
                    response,
                    "Не удалось удалить адрес из избранного",
                ),
            );
        }

        // Успешный DELETE возвращает 204 без JSON-тела.
        return true;
    }

    window.FavoritesApi = {
        loadFavoriteSenders,
        createFavoriteSender,
        updateFavoriteSender,
        deleteFavoriteSender,
    };
})();