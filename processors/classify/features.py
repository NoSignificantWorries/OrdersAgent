import re
from typing import Any, Dict, List


class FeaturesExtractor:
    @classmethod
    def extract_text_features(cls, text: str) -> Dict[str, Any]:
        text_lower = text.lower().strip()

        # =========================================================
        # 1. Слова-триггеры для разных классов
        # =========================================================

        # REQUEST - подтверждение/запуск
        request_words = [
            "подтверждаю",
            "подтвердить",
            "подтверждение",
            "в работу",
            "запустить",
            "запускайте",
            "запускается",
            "счет в работу",
            "счёт в работу",
            "заказ подтверждаю",
            "прошу запустить",
            "готов к отправке",
            "отправка:",
            "запускается только после согласования счета",
            "отгрузка изделий",
        ]

        # CALCULATION - просьба посчитать
        calc_words = [
            "посчитайте",
            "рассчитайте",
            "просчитайте",
            "расчёт",
            "расчет",
            "рассчитать",
            "сроки поставки",
            "срок поставки",
            "ориентировочную стоимость",
            "сколько будет стоить",
            "делаете ли такие",
            "возможна ли",
            "какая ближайшая дата",
            "в расчет",
            "в расчёт",
            "запрос стоимости",
            "ценовой запрос",
        ]

        # CALCULATION - слова-маркеры цены/сроков
        price_deadline_words = [
            "стоимость",
            "цену",
            "цена",
            "цены",
            "срок",
            "сроки",
        ]

        # QUESTION - вопросительные слова
        question_words = [
            "вопрос",
            "подскажите",
            "уточните",
            "готов ли",
            "когда будет готов",
            "не пришёл",
            "не получили",
            "ошибка",
            "что с",
            "где заказ",
            "статус заказа",
            "проверьте",
            "интересует",
            "можно ли",
            "почему",
            "зачем",
        ]

        # Счёт/оплата (нейтральный маркер, важен в комбинациях)
        invoice_words = [
            "счет",
            "счёт",
            "оплата",
            "оплатить",
        ]

        # Заявка (нейтральный маркер)
        request_form_words = [
            "заявка",
            "заявку",
        ]

        # =========================================================
        # 2. Проверка наличия слов
        # =========================================================

        def check_any(words_list: list) -> bool:
            return any(word in text_lower for word in words_list)

        has_request_word = check_any(request_words)
        has_calc_word = check_any(calc_words)
        has_price_deadline_word = check_any(price_deadline_words)
        has_question_word = check_any(question_words)
        has_invoice_word = check_any(invoice_words)
        has_request_form_word = check_any(request_form_words)

        # =========================================================
        # 3. Структурные признаки
        # =========================================================

        has_question_mark = "?" in text
        has_exclamation = "!" in text
        text_length = len(text)
        word_count = len(text.split())
        is_very_short = text_length < 100
        is_empty_or_only_greeting = text_length < 50 and "здравствуйте" in text_lower

        # =========================================================
        # 4. Паттерны (регулярные выражения)
        # =========================================================

        # Номер счёта (5 и более цифр подряд, опционально с №)
        has_invoice_number = bool(re.search(r"№?\s*\d{5,}", text))

        # Дата в форматах: 11.03.26, 11.03.2026, 11-03-26
        has_date = bool(re.search(r"\d{2}[./-]\d{2}[./-]\d{2,4}", text))

        # Заявка с номером
        has_request_with_number = bool(
            re.search(r"заявка\s*№?\s*\d+", text_lower)
            or re.search(r"заявка\s+на\s+стеклопакеты\s*№\s*\d+", text_lower)
        )

        # =========================================================
        # 5. Комбинированные признаки
        # =========================================================

        # REQUEST: много признаков готовой заявки
        is_request_likely = (
            has_request_word
            or has_invoice_number
            or (has_request_form_word and not has_calc_word)
        )

        # CALCULATION: просьба посчитать
        is_calculation_likely = (
            has_calc_word
            or (has_price_deadline_word and has_invoice_word)
            or (has_price_deadline_word and not has_request_word)
        )

        # QUESTION: вопросительные маркеры
        is_question_likely = (
            has_question_word
            or (has_question_mark and is_very_short)
            or (has_question_mark and word_count < 10)
            or (has_question_mark and not has_invoice_number and not has_date)
        )

        # =========================================================
        # 6. Итоговый словарь признаков
        # =========================================================

        features = {
            # Базовые триггеры
            "has_request_word": has_request_word,
            "has_calc_word": has_calc_word,
            "has_question_word": has_question_word,
            "has_price_deadline_word": has_price_deadline_word,
            "has_invoice_word": has_invoice_word,
            "has_request_form_word": has_request_form_word,
            # Структурные
            "has_question_mark": has_question_mark,
            "has_exclamation": has_exclamation,
            "text_length": text_length,
            "word_count": word_count,
            "is_very_short": is_very_short,
            "is_empty_or_only_greeting": is_empty_or_only_greeting,
            # Паттерны
            "has_invoice_number": has_invoice_number,
            "has_date": has_date,
            "has_request_with_number": has_request_with_number,
            # Комбинированные (сильные признаки)
            "is_request_likely": is_request_likely,
            "is_calculation_likely": is_calculation_likely,
            "is_question_likely": is_question_likely,
            "calc_with_invoice_pattern": (has_calc_word and has_invoice_word),
        }

        return features

    @classmethod
    def extract_files_features(cls, files: List[str]) -> Dict[str, Any]:
        has_xlsx = False
        count_files = 0
        for file in files:
            matched = re.match(r"^(.+)\.([a-z]+)$", file)
            suffix = ""
            if matched:
                suffix = matched.group(2)
            if suffix in ["xls", "xlsx"]:
                count_files += 1
                has_xlsx = True
        return {"xlsx_count": count_files, "has_xlsx": has_xlsx}
