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
        
        const isEmailDate = dateString.includes('+00:00') && 
                            dateString.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
        
        if (isEmailDate) {
            // Показываем как есть (в UTC)
            return date.toLocaleString("ru-RU", {
                timeZone: "UTC",
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
        
        // Для createdat - конвертируем в Новосибирск
        return date.toLocaleString("ru-RU", {
            timeZone: "Asia/Novosibirsk",
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
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
        pluralizeRu,
        formatUnreadCount,
        mapTaskStatusToUiStatus,
        getStatusName,
    };
})();