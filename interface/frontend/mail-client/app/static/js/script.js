// ===== РЕАЛЬНЫЕ ПИСЬМА ИЗ ВАШЕЙ ПОЧТЫ =====
const emails = [
    {
        id: 1,
        sender: "Наталья Парфенова",
        email: "n.parfenova@m1glass.ru",
        subject: "Заявка на стеклопакеты №1283A, 1282A, 1281A, 1224A, 1251A, 9_24246, 303008467",
        preview: "Здравствуйте, С уважением, Наталья Парфенова Менеджер отдела продаж ООО 'М1'...",
        date: "2026-03-13",
        status: "waiting",
        content: `Здравствуйте,

Направляю заявку на стеклопакеты:
• №1283A
• №1282A
• №1281A
• №1224A
• №1251A
• 9_24246
• 303008467

Даты доставки: 02.03.26, 11.03.26

Прикрепленные файлы:
• 1283A.xls
• 1282A.xls
• 1281A.xls
• 1224A.xls
• 1251A.xls
• 9_24246.xls
• 303008467.xls

С уважением, Наталья Парфенова
Менеджер отдела продаж ООО "М1"
(383)362-00-01 доб.114
n.parfenova@m1glass.ru`
    },
    {
        id: 2,
        sender: "Наталья Парфенова",
        email: "n.parfenova@m1glass.ru",
        subject: "Заявка на стеклопакеты №1298A, 1297A, 1296A, 1259A, 079036108, 079038833",
        preview: "Здравствуйте, С уважением, Наталья Парфенова Менеджер отдела продаж ООО 'М1'...",
        date: "2026-03-13",
        status: "processing",
        content: `Здравствуйте,

Направляю заявку на стеклопакеты:
• №1298A
• №1297A
• №1296A
• №1259A
• 079036108
• 079038833

Дата доставки: 04.03.26

Прикрепленные файлы:
• 1298A.xls
• 1297A.xls
• 1296A.xls
• 1259A.xls
• 079036108.xls
• 079038833.xls

С уважением, Наталья Парфенова
Менеджер отдела продаж ООО "М1"
(383)362-00-01 доб.114
n.parfenova@m1glass.ru`
    },
    {
        id: 3,
        sender: "Наталья Парфенова",
        email: "n.parfenova@m1glass.ru",
        subject: "Запрос стоимости",
        preview: "Здравствуйте, С уважением, Наталья Парфенова...",
        date: "2026-03-13",
        status: "clarification",
        content: `Здравствуйте,

Прошу рассчитать стоимость по приложенной заявке.

Прикрепленные файлы:
• Заявка 27.02.26.xls

С уважением, Наталья Парфенова
Менеджер отдела продаж ООО "М1"
(383)362-00-01 доб.114
n.parfenova@m1glass.ru`
    },
    {
        id: 4,
        sender: "Наталья Парфенова",
        email: "n.parfenova@m1glass.ru",
        subject: "Заявка на расчет ИП Колодинов С.С.",
        preview: "Здравствуйте, С уважением, Наталья Парфенова...",
        date: "2026-03-13",
        status: "completed",
        content: `Здравствуйте,

Прошу произвести расчет для ИП Колодинов С.С.

Прикрепленные файлы:
• Заявка М1 от 05.03... кат.xls
• Приложение к заявке... -22.pdf
• Приложение к заявке... -26.pdf

С уважением, Наталья Парфенова
Менеджер отдела продаж ООО "М1"
(383)362-00-01 доб.114
n.parfenova@m1glass.ru`
    },
    {
        id: 5,
        sender: "Наталья Парфенова",
        email: "n.parfenova@m1glass.ru",
        subject: "Заявка на стеклопакеты №1250A, 1249A, 1248A, 1247A, 1246A, 1240A, 05502547, 079038775, 012237682",
        preview: "Здравствуйте, С уважением, Наталья Парфенова...",
        date: "2026-03-13",
        status: "waiting",
        content: `Здравствуйте,

Направляю заявку на стеклопакеты:
• №1250A
• №1249A
• №1248A
• №1247A
• №1246A
• №1240A
• 05502547
• 079038775
• 012237682

Даты доставки: 23.02.26, 24.02.26, 04.03.26, 12.03.26, 19.03.26

Прикрепленные файлы:
• 1250A.xls
• 1249A.xls
• 1248A.xls
• 1247A.xls
• 1246A.xls
• 1240A.xls
• 05502547.xls
• 079038775.xls
• 012237682.xls
• 012237682-01
• 2237682.pdf

С уважением, Наталья Парфенова
Менеджер отдела продаж ООО "М1"
(383)362-00-01 доб.114
n.parfenova@m1glass.ru`
    },
    {
        id: 6,
        sender: "Наталья Парфенова",
        email: "n.parfenova@m1glass.ru",
        subject: "ЖК Счастливый квартал. Заявка на стеклопакеты №1271А, 1271В, 1271С, 1272А, 1272В, 1272С, 1273А, 1273В, 1273С, 1274А, 1274В, 1274С",
        preview: "Здравствуйте, С уважением, Наталья Парфенова...",
        date: "2026-03-13",
        status: "processing",
        content: `Здравствуйте,

Направляю заявку на стеклопакеты для ЖК "Счастливый квартал":
• №1271А, 1271В, 1271С
• №1272А, 1272В, 1272С
• №1273А, 1273В, 1273С
• №1274А, 1274В, 1274С

Даты доставки: 12.03.26, 20.03.26, 31.03.26, 10.04.26

С уважением, Наталья Парфенова
Менеджер отдела продаж ООО "М1"
(383)362-00-01 доб.114
n.parfenova@m1glass.ru`
    }
];

// ===== КОНФИГУРАЦИЯ СТАТУСОВ =====
const statusConfig = {
    waiting: {
        name: "Ожидание",
        color: "#d97706",
        bg: "#fef3c7",
        border: "#f59e0b"
    },
    processing: {
        name: "Обработка",
        color: "#2563eb",
        bg: "#dbeafe",
        border: "#3b82f6"
    },
    clarification: {
        name: "Уточнение",
        color: "#0891b2",
        bg: "#cffafe",
        border: "#06b6d4"
    },
    completed: {
        name: "Выполнена",
        color: "#16a34a",
        bg: "#dcfce7",
        border: "#22c55e"
    }
};

// ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

function formatDate(dateString) {
    const date = new Date(dateString);
    const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    return `${date.getDate()} ${months[date.getMonth()]}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoading() {
    const emailView = document.getElementById('emailView');
    if (emailView) {
        emailView.innerHTML = `<div style="display: flex; justify-content: center; align-items: center; height: 300px;"><div class="loading"></div></div>`;
    }
}

// ===== ФУНКЦИЯ УДАЛЕНИЯ ПИСЬМА =====
function deleteEmail(emailId) {
    const index = emails.findIndex(e => e.id === parseInt(emailId));
    if (index !== -1) {
        emails.splice(index, 1);
        
        renderEmailList();
        
        if (emails.length > 0) {
            selectEmail(emails[0].id);
        } else {
            const emailView = document.getElementById('emailView');
            if (emailView) {
                emailView.innerHTML = `
                    <div class="email-placeholder">
                        📭 Нет писем для обработки
                    </div>
                `;
            }
        }
        
        console.log(`Письмо ${emailId} удалено`);
    }
}

// ===== ОСНОВНЫЕ ФУНКЦИИ =====

function renderEmailList() {
    const container = document.getElementById('emailsContainer');
    if (!container) return;

    const sortedEmails = [...emails].sort((a, b) => new Date(b.date) - new Date(a.date));

    container.innerHTML = sortedEmails.map(email => {
        const status = statusConfig[email.status] || statusConfig.waiting;
        return `
            <div class="email-item" data-id="${email.id}">
                <div class="email-item-header">
                    <div class="sender">${escapeHtml(email.sender)}</div>
                    <div class="status-badge" style="background: ${status.bg}; color: ${status.color}; border-color: ${status.border};">
                        ${status.name}
                    </div>
                </div>
                <div class="subject">${escapeHtml(email.subject)}</div>
                <div class="preview">${escapeHtml(email.preview)}</div>
                <div class="date">${formatDate(email.date)}</div>
            </div>
        `;
    }).join('');

    document.querySelectorAll('.email-item').forEach(item => {
        item.addEventListener('click', () => selectEmail(item.dataset.id));
    });
}

function selectEmail(id) {
    showLoading();

    setTimeout(() => {
        document.querySelectorAll('.email-item').forEach(item => {
            item.classList.remove('selected');
        });

        const selectedItem = document.querySelector(`.email-item[data-id="${id}"]`);
        if (selectedItem) {
            selectedItem.classList.add('selected');
        }

        const email = emails.find(e => e.id == parseInt(id));
        if (!email) return;

        const currentStatus = statusConfig[email.status] || statusConfig.waiting;
        
        const formattedContent = email.content
            .split('\n')
            .map(line => {
                if (line.trim() === '') return '<br>';
                if (line.includes('•')) return `<p style="margin-left: 20px;">${escapeHtml(line)}</p>`;
                return `<p>${escapeHtml(line)}</p>`;
            })
            .join('');

        const showAcceptButton = email.status === "completed";
        
        const emailView = document.getElementById('emailView');
        emailView.innerHTML = `
            <div class="email-card">
                <div class="email-header">
                    <div class="email-subject">${escapeHtml(email.subject)}</div>
                    
                    <div class="status-block">
                        <div class="status-info">
                            <span class="status-label">Состояние:</span>
                            <div class="status-display" style="background: ${currentStatus.bg}; color: ${currentStatus.color}; border: 2px solid ${currentStatus.border};">
                                ${currentStatus.name}
                            </div>
                        </div>
                    </div>
                    
                    <div class="email-meta">
                        <div><strong>От:</strong> ${escapeHtml(email.sender)} (${escapeHtml(email.email)})</div>
                        <div><strong>Дата:</strong> ${email.date}</div>
                    </div>
                </div>
                <div class="email-body">
                    ${formattedContent}
                </div>
                ${showAcceptButton ? `
                <div class="accept-button-container">
                    <button class="accept-btn" data-id="${email.id}">
                        ✅ Принять
                    </button>
                </div>
                ` : ''}
            </div>
        `;

        if (showAcceptButton) {
            const acceptBtn = document.querySelector('.accept-btn');
            if (acceptBtn) {
                acceptBtn.addEventListener('click', (e) => {
                    const emailId = e.target.dataset.id;
                    deleteEmail(emailId);
                });
            }
        }
    }, 300);
}

// ===== ИНИЦИАЛИЗАЦИЯ =====
document.addEventListener('DOMContentLoaded', () => {
    renderEmailList();
    if (emails.length > 0) {
        selectEmail(emails[0].id);
    }
});

window.mailClient = { emails, deleteEmail, statusConfig };