(function () {
    const statusConfig = {
        waiting: { name: "Ожидание" },
        processing: { name: "Обработка" },
        ml_review: { name: "Выберите класс" },
        materials_review: { name: "Требуются материалы" },
        question: { name: "Вопрос" },
        completed: { name: "Завершено" },
        error: { name: "Ошибка" },
    };

    function formatDate(dateString) {
        const date = new Date(dateString);
        if (isNaN(date)) return "";

        const months = [
            "янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек",
        ];

        return `${date.getDate()} ${months[date.getMonth()]}`;
    }

    function formatDateTime(dateString) {
        const date = new Date(dateString);
        if (isNaN(date)) return "";
        return date.toLocaleString("ru-RU");
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
        escapeHtml,
        escapeAttr,
        mapTaskStatusToUiStatus,
        getStatusName,
    };
})();