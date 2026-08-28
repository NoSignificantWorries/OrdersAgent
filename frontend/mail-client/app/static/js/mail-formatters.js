(function () {
    const statusConfig = {
        waiting: { name: "Ожидание" },
        processing: { name: "Обработка" },
        ml_review: { name: "Выберите класс" },
        materials_review: { name: "Требуются материалы" },
        question: { name: "Вопрос" },
        claim: { name: "Претензия" },
        completed: { name: "Завершено" },
        error: { name: "Ошибка" },
    };

    function formatDate(dateString) {
        const formatted = formatDateTime(dateString);
        if (!formatted) return "";

        const match = formatted.match(/^(\d{2})\.(\d{2})\.(\d{4})/);
        if (!match) return "";

        const months = [
            "янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек",
        ];

        const day = String(Number(match[1]));
        const monthIndex = Number(match[2]) - 1;

        if (monthIndex < 0 || monthIndex > 11) return "";

        return `${day} ${months[monthIndex]}`;
    }

    function formatDateTime(dateString) {
        if (!dateString) return "";
        const raw = String(dateString).trim();
        if (!raw || raw.startsWith("0001-01-01")) return "";

        const date = new Date(raw);
        if (isNaN(date)) return "";

        return date.toLocaleString("ru-RU", {
            timeZone: "Asia/Novosibirsk",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit"
        });
    }

    function formatTimeOnly(dateString) {
        if (!dateString) return "";
        const raw = String(dateString).trim();
        if (!raw || raw.startsWith("0001-01-01")) return "";

        const date = new Date(raw);
        if (isNaN(date)) return "";

        return date.toLocaleString("ru-RU", {
            timeZone: "Asia/Novosibirsk",
            hour: "2-digit",
            minute: "2-digit"
        });
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text ?? "";
        return div.innerHTML;
    }

    function escapeAttr(text) {
        return String(text ?? "")
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;");
    }

    function decodeHtmlEntities(value) {
        const source = String(value || "");

        if (!source) {
            return "";
        }

        const textarea = document.createElement("textarea");
        textarea.innerHTML = source;

        return textarea.value;
    }

    function hasHtmlMarkup(value) {
        const text = String(value || "").trim();

        if (!text) {
            return false;
        }

        return /<\/?(?:html|head|body|div|p|br|span|table|thead|tbody|tfoot|tr|th|td|ul|ol|li|blockquote|pre|a|strong|b|em|i|u)\b[^>]*>/i.test(
            text,
        );
    }

    function htmlToPlainText(value) {
        const source = String(value || "");

        if (!source.trim()) {
            return "";
        }

        const decoded = decodeHtmlEntities(source);

        if (!hasHtmlMarkup(decoded)) {
            return decoded
                .replace(/\r\n/g, "\n")
                .replace(/\r/g, "\n")
                .replace(/\n{3,}/g, "\n\n")
                .trim();
        }

        const doc = new DOMParser().parseFromString(decoded, "text/html");

        doc.querySelectorAll(
            [
                "script",
                "style",
                "noscript",
                "iframe",
                "object",
                "embed",
                "form",
                "input",
                "button",
                "textarea",
                "select",
                "option",
                "link",
                "meta",
                "base",
                "svg",
                "math",
            ].join(", "),
        ).forEach((node) => node.remove());

        doc.querySelectorAll("br").forEach((node) => {
            node.replaceWith(document.createTextNode("\n"));
        });

        doc.querySelectorAll(
            [
                "p",
                "div",
                "section",
                "article",
                "header",
                "footer",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "li",
                "tr",
                "blockquote",
                "pre",
            ].join(", "),
        ).forEach((node) => {
            node.appendChild(document.createTextNode("\n"));
        });

        doc.querySelectorAll("th, td").forEach((node) => {
            node.appendChild(document.createTextNode("\t"));
        });

        return String(doc.body.textContent || "")
            .replace(/\u00a0/g, " ")
            .replace(/[ \t]+\n/g, "\n")
            .replace(/\n[ \t]+/g, "\n")
            .replace(/\n{3,}/g, "\n\n")
            .trim();
    }

    function pluralizeRu(count, one, few, many) {
        const abs = Math.abs(Number(count)) % 100;
        const last = abs % 10;

        if (abs > 10 && abs < 20) return many;
        if (last === 1) return one;
        if (last >= 2 && last <= 4) return few;
        return many;
    }

    function formatUnreadCount(count) {
        return `${count} ${pluralizeRu(
            count,
            "непрочитанное",
            "непрочитанных",
            "непрочитанных",
        )}`;
    }

    function mapTaskStatusToUiStatus(taskStatus) {
        switch ((taskStatus || "").toLowerCase()) {
            case "new":
                return "waiting";

            case "downloaded":
                return "waiting";

            case "files_saved":
                return "waiting";

            case "ml_review":
                return "ml_review";

            case "materials_review":
                return "materials_review";

            case "ml_classified":
                return "processing";

            case "manual_review_done":
                return "processing";

            case "question":
                return "question";

            case "claim":
                return "claim";

            case "completed":
                return "completed";

            case "error":
                return "error";

            default:
                return "processing";
        }
    }

    function getStatusName(uiStatus) {
        return statusConfig[uiStatus]?.name || "Неизвестно";
    }

    window.MailFormatters = {
        statusConfig,
        formatDate,
        formatDateTime,
        formatTimeOnly,
        escapeHtml,
        escapeAttr,
        decodeHtmlEntities,
        hasHtmlMarkup,
        htmlToPlainText,
        pluralizeRu,
        formatUnreadCount,
        mapTaskStatusToUiStatus,
        getStatusName,
    };
})();