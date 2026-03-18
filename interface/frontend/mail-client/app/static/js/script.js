// ===== ТЕСТОВЫЕ ДАННЫЕ ПИСЕМ =====
const emails = [
    {
        id: 1,
        sender: "Сбербанк",
        email: "info@sberbank.ru",
        subject: "Изменение условий обслуживания",
        preview: "Уважаемый клиент, информируем вас об изменении тарифов на обслуживание корпоративных карт с 1 марта 2024 года...",
        date: "2024-01-15",
        content: `Уважаемый клиент!
        
С 1 марта 2024 года вступают в силу новые условия обслуживания корпоративных карт.

🔹 **Основные изменения:**
• Увеличение кешбэка до 5% на все операции
• Бесплатное обслуживание при обороте от 100 000 ₽ в месяц
• Новые лимиты на снятие наличных: до 150 000 ₽ в сутки
• Добавлена возможность бесплатных переводов между картами Сбера

🔹 **Как подготовиться:**
1. Обновите приложение СберБанк Бизнес
2. Ознакомьтесь с полными условиями в личном кабинете
3. При необходимости измените тарифный план

Если у вас возникнут вопросы, наша поддержка работает 24/7 по телефону 900.

С уважением,
Команда Сбербанка

---

📌 *Это тестовое письмо для демонстрации интерфейса*`
    },
    {
        id: 2,
        sender: "Яндекс.Такси",
        email: "taxi@yandex.ru",
        subject: "Отчёт за январь 2024",
        preview: "Ваш отчёт по поездкам за январь: 23 поездки на сумму 4 890 ₽, бонусы 300 ₽...",
        date: "2024-01-14",
        content: `Здравствуйте!

Подготовили для вас отчёт по поездкам за январь 2024 года:

📊 **Статистика:**
• Всего поездок: 23
• Сумма: 4 890 ₽
• Средний чек: 212 ₽
• Бонусы: 300 ₽
• Любимый тариф: Эконом

🏆 **Достижения:**
• Самый длинный маршрут: 45 км (аэропорт)
• Самая ранняя поездка: 5:30 утра
• Самая поздняя: 2:15 ночи

🎁 **Бонусы:**
300 бонусов зачислены на ваш счёт. Их можно потратить на следующие поездки.

Скачать детализацию можно по ссылке: https://taxi.yandex.ru/reports/jan2024

Спасибо что выбираете Яндекс.Такси!

---

📌 *Это тестовое письмо для демонстрации интерфейса*`
    },
    {
        id: 3,
        sender: "Wildberries",
        email: "support@wb.ru",
        subject: "Заказ №45892 доставлен в пункт выдачи",
        preview: "Ваш заказ прибыл. Адрес: ул. Ленина, 10. Состав: Ноутбук Lenovo, Мышь беспроводная...",
        date: "2024-01-13",
        content: `Здравствуйте!

Рады сообщить, что ваш заказ №45892 прибыл в пункт выдачи!

📍 **Адрес получения:**
ул. Ленина, 10, ТЦ "Центральный", 2 этаж, пункт Wildberries
Режим работы: ежедневно 9:00 - 22:00

📦 **Состав заказа:**
1. Ноутбук Lenovo IdeaPad 3 (арт. 123456) - 1 шт
2. Мышь беспроводная Logitech (арт. 789012) - 1 шт
3. Сумка для ноутбука (арт. 345678) - 1 шт

⏳ **Срок хранения:**
Забрать заказ нужно до 25 января 2024. После этого заказ будет отменён.

📱 **Как получить:**
• Покажите QR-код из приложения
• Или назовите номер заказа сотруднику

С уважением,
Wildberries

---

📌 *Это тестовое письмо для демонстрации интерфейса*`
    },
    {
        id: 4,
        sender: "Тинькофф",
        email: "bank@tinkoff.ru",
        subject: "Кэшбэк за январь: 1 234 ₽",
        preview: "Вам начислен кэшбэк 1 234 рубля. Средства уже доступны в приложении...",
        date: "2024-01-12",
        content: `Здравствуйте!

Зачисляем кэшбэк за январь! 🎉

💰 **Сумма кэшбэка: 1 234 ₽**

📊 **Детализация:**
• Продукты: 345 ₽ (категория 5%)
• Рестораны: 234 ₽ (категория 3%)
• Транспорт: 156 ₽ (категория 2%)
• Аптеки: 499 ₽ (категория 10%)

💡 **Что можно сделать:**
• Потратить у партнёров с повышенным кэшбэком
• Перевести на вклад под проценты
• Обменять на мили S7
• Отправить близким

📱 Средства уже доступны в приложении Тинькофф.

Спасибо, что вы с нами!

---

📌 *Это тестовое письмо для демонстрации интерфейса*`
    },
    {
        id: 5,
        sender: "Ozon",
        email: "info@ozon.ru",
        subject: "🔥 Мегараспродажа: скидки до 50% на электронику",
        preview: "Только до конца недели: смартфоны со скидкой 40%, ноутбуки - 50%, аксессуары - 30%...",
        date: "2024-01-11",
        content: `Специальное предложение для вас! 🔥

Только до конца недели действуют суперскидки на электронику:

📱 **Смартфоны:**
• Apple iPhone 15 - 79 990 ₽ (было 99 990 ₽)
• Samsung Galaxy S23 - 54 990 ₽ (было 69 990 ₽)
• Xiaomi 13T - 39 990 ₽ (было 49 990 ₽)

💻 **Ноутбуки:**
• Apple MacBook Air M2 - 89 990 ₽ (было 119 990 ₽)
• ASUS ZenBook - 59 990 ₽ (было 79 990 ₽)
• Lenovo IdeaPad - 34 990 ₽ (было 49 990 ₽)

🎧 **Аксессуары:**
• Наушники Apple AirPods Pro - 15 990 ₽ (было 24 990 ₽)
• Умные часы Samsung - 12 990 ₽ (было 18 990 ₽)
• Внешние аккумуляторы - от 990 ₽

⏰ Акция действует до 18 января включительно.

Переходите в приложение Ozon и успевайте купить по выгодным ценам!

Ozon - миллионы товаров по лучшим ценам

---

📌 *Это тестовое письмо для демонстрации интерфейса*`
    }
];

// ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

/**
 * Форматирование даты в читаемый вид
 * @param {string} dateString - дата в формате YYYY-MM-DD
 * @returns {string} отформатированная дата
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    const months = [
        'янв', 'фев', 'мар', 'апр', 'май', 'июн',
        'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
    ];
    const day = date.getDate();
    const month = months[date.getMonth()];
    return `${day} ${month}`;
}

/**
 * Экранирование HTML-символов для безопасности
 * @param {string} text - текст для экранирования
 * @returns {string} безопасный текст
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Показывает индикатор загрузки
 */
function showLoading() {
    const emailView = document.getElementById('emailView');
    if (emailView) {
        emailView.innerHTML = `
            <div style="display: flex; justify-content: center; align-items: center; height: 300px;">
                <div class="loading"></div>
            </div>
        `;
    }
}

// ===== ОСНОВНЫЕ ФУНКЦИИ =====

/**
 * Отображение списка писем в левой панели
 */
function renderEmailList() {
    const container = document.getElementById('emailsContainer');
    if (!container) return;

    // Очищаем контейнер
    container.innerHTML = '';

    // Сортируем письма по дате (новые сверху)
    const sortedEmails = [...emails].sort((a, b) => 
        new Date(b.date) - new Date(a.date)
    );

    // Создаем элементы для каждого письма
    sortedEmails.forEach(email => {
        const emailElement = document.createElement('div');
        emailElement.className = 'email-item';
        emailElement.dataset.id = email.id;
        
        // Добавляем класс "unread" для непрочитанных (первые 3 письма)
        if (email.id <= 3) {
            emailElement.classList.add('unread');
        }

        emailElement.innerHTML = `
            <div class="sender">${escapeHtml(email.sender)}</div>
            <div class="subject">${escapeHtml(email.subject)}</div>
            <div class="preview">${escapeHtml(email.preview)}</div>
            <div class="date">${formatDate(email.date)}</div>
        `;

        // Добавляем обработчик клика
        emailElement.addEventListener('click', () => selectEmail(email.id));
        
        container.appendChild(emailElement);
    });

    // Автоматически выбираем первое письмо
    if (emails.length > 0) {
        selectEmail(emails[0].id);
    }
}

/**
 * Выбор письма по ID
 * @param {number} id - ID письма
 */
function selectEmail(id) {
    // Показываем загрузку
    showLoading();

    // Небольшая задержка для демонстрации загрузки (можно убрать)
    setTimeout(() => {
        // Убираем выделение со всех писем
        document.querySelectorAll('.email-item').forEach(item => {
            item.classList.remove('selected');
        });

        // Выделяем выбранное письмо
        const selectedItem = document.querySelector(`.email-item[data-id="${id}"]`);
        if (selectedItem) {
            selectedItem.classList.add('selected');
            
            // Убираем маркер непрочитанного
            selectedItem.classList.remove('unread');
        }

        // Находим данные письма
        const email = emails.find(e => e.id === parseInt(id));
        if (!email) return;

        // Отображаем содержимое
        const emailView = document.getElementById('emailView');
        
        // Форматируем содержимое с поддержкой переносов строк
        const formattedContent = email.content
            .split('\n')
            .map(line => {
                if (line.trim() === '') return '<br>';
                if (line.includes('🔹') || line.includes('📊') || line.includes('📍')) {
                    return `<p style="font-weight: 600; margin-top: 15px;">${escapeHtml(line)}</p>`;
                }
                if (line.includes('•')) {
                    return `<p style="margin-left: 20px; color: #475569;">${escapeHtml(line)}</p>`;
                }
                return `<p>${escapeHtml(line)}</p>`;
            })
            .join('');

        emailView.innerHTML = `
            <div class="email-card">
                <div class="email-header">
                    <div class="email-subject">${escapeHtml(email.subject)}</div>
                    <div class="email-meta">
                        <div><strong>От:</strong> ${escapeHtml(email.sender)} (${escapeHtml(email.email)})</div>
                        <div><strong>Кому:</strong> me@company.ru</div>
                        <div><strong>Дата:</strong> ${email.date}</div>
                    </div>
                </div>
                <div class="email-body">
                    ${formattedContent}
                </div>
            </div>
        `;
    }, 300); // Небольшая задержка для демонстрации загрузки
}

/**
 * Поиск писем (функция для будущего использования)
 * @param {string} query - поисковый запрос
 */
function searchEmails(query) {
    if (!query.trim()) {
        renderEmailList();
        return;
    }

    const filtered = emails.filter(email => 
        email.sender.toLowerCase().includes(query.toLowerCase()) ||
        email.subject.toLowerCase().includes(query.toLowerCase()) ||
        email.preview.toLowerCase().includes(query.toLowerCase())
    );

    // Здесь можно реализовать отображение отфильтрованных писем
    console.log('Найдено писем:', filtered.length);
}

/**
 * Обновление счетчика непрочитанных писем
 */
function updateUnreadCount() {
    const unreadCount = document.querySelectorAll('.email-item.unread').length;
    const countElement = document.querySelector('.email-count');
    if (countElement) {
        countElement.textContent = `${unreadCount} непрочитанных`;
    }
}

// ===== ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ =====
document.addEventListener('DOMContentLoaded', () => {
    console.log('Приложение загружено, инициализация...');
    
    // Отображаем список писем
    renderEmailList();
    
    // Обновляем счетчик
    updateUnreadCount();

    // Добавляем обработчик для кнопки выхода (если есть)
    const logoutBtn = document.querySelector('.logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            console.log('Выход из системы');
            // Здесь будет логика выхода
        });
    }

    // Добавляем обработчик для поиска (если добавите поле поиска)
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchEmails(e.target.value);
        });
    }

    console.log('Инициализация завершена');
});

// ===== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ БУДУЩЕГО =====

/**
 * Отметить письмо как прочитанное
 * @param {number} id - ID письма
 */
function markAsRead(id) {
    const emailItem = document.querySelector(`.email-item[data-id="${id}"]`);
    if (emailItem) {
        emailItem.classList.remove('unread');
        updateUnreadCount();
    }
}

/**
 * Удалить письмо
 * @param {number} id - ID письма
 */
function deleteEmail(id) {
    const index = emails.findIndex(e => e.id === id);
    if (index !== -1) {
        emails.splice(index, 1);
        renderEmailList();
        updateUnreadCount();
    }
}

/**
 * Обновить список писем (для будущей синхронизации)
 */
function refreshEmails() {
    showLoading();
    setTimeout(() => {
        renderEmailList();
        updateUnreadCount();
    }, 1000);
}

// Экспортируем функции для глобального доступа (если нужно)
window.mailClient = {
    selectEmail,
    searchEmails,
    refreshEmails,
    deleteEmail,
    markAsRead
};