import json

class TestEngine:
    def __init__(self):
        # Вопросы уже есть в вашем файле, оставляем как есть
        self.questions = [
            {"text": "Как часто вы теряете эмоциональное равновесие?", "type": "single",
             "options": ["Практически никогда", "Редко", "Иногда", "Часто"]},
            {"text": "В каких сферах вам труднее всего справляться с собой?", "type": "multi",
             "options": ["Отношения", "Работа", "Самооценка", "Здоровье", "Финансы", "Перемены"]},
            {"text": "Что чаще всего помогает вам в трудные моменты?", "type": "multi",
             "options": ["Друзья", "Книги/Видео", "Спорт", "Еда/Альтернатива", "Психолог"]},
            {"text": "Что для вас главное, когда вы делитесь переживаниями?", "type": "single",
             "options": ["Не делюсь", "Понять, что не одинок", "Разобраться"]},
            {"text": "Что вы чувствуете после того как справились?", "type": "single",
             "options": ["Лёгкость", "Гордость", "Желание поделиться", "Усталость"]},
            {"text": "Как вы реагируете на истории других людей?", "type": "single",
             "options": ["Избегаю", "Молчу", "Сравниваю", "Сопереживаю"]},
            {"text": "Как вы воспринимаете обратную связь?", "type": "single",
             "options": ["Болезненно", "Игнорирую", "Как идеи", "Как инструмент"]},
            {"text": "Как вы замечаете свои успехи?", "type": "single",
             "options": ["Сам", "Дневник/Трекер", "Признание других", "С психологом"]},
            {"text": "Важно ли вам делиться опытом, чтобы помочь другим?", "type": "single", "options": ["Да", "Нет"]},
            {"text": "Вам легко говорить о своих чувствах?", "type": "single",
             "options": ["Скрываю", "По ситуации", "Только с близкими", "Да, это сила"]},
            {"text": "Что для вас главное в работе над собой?", "type": "single",
             "options": ["Шаги", "Поддержка", "Новый взгляд", "Глубина"]}
        ]
    
    def get_total_questions(self):
        return len(self.questions)

    def get_question(self, index):
        """Возвращает данные вопроса по индексу."""
        if 0 <= index < len(self.questions):
            return self.questions[index]
        return None

    def serialize_answers(self, answers_dict):
        """Превращает словарь ответов {q_id: [indices]} в строку для БД."""
        # Преобразуем ключи в строки для JSON
        serializable_dict = {str(k): v for k, v in answers_dict.items()}
        return json.dumps(serializable_dict)

    def deserialize_answers(self, answers_str):
        """Превращает строку из БД обратно в словарь."""
        if not answers_str:
            return {}
        
        try:
            data = json.loads(answers_str)
            # Преобразуем ключи обратно в int
            return {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, ValueError):
            return {}

    def calculate_similarity(self, user_a_ans, user_b_ans):
        """
        Сравнивает два набора ответов. 
        Возвращает float от 0.0 до 1.0 (процент схожести).
        """
        total_weight = 0
        matches = 0

        for i in range(len(self.questions)):
            a = set(user_a_ans.get(i, []))
            b = set(user_b_ans.get(i, []))

            # Вес вопроса (можно настроить, чтобы некоторые вопросы весили больше)
            weight = 1.5 if self.questions[i]['type'] == 'multi' else 1.0
            total_weight += weight

            if a == b and a:  # Идентичные ответы
                matches += weight
            elif a & b:  # Частичное совпадение (актуально для multi)
                intersection_ratio = len(a & b) / len(a | b)
                matches += weight * intersection_ratio

        if total_weight == 0:
            return 0.0
        
        return round(matches / total_weight, 2)

    def find_matches(self, target_user_ans, all_users_from_db, top_n=5):
        """
        Ищет топ похожих людей.
        all_users_from_db: список кортежей/словарей [(user_id, answers_json), ...]
        """
        results = []
        for uid, ans_json in all_users_from_db:
            other_ans = self.deserialize_answers(ans_json)
            sim = self.calculate_similarity(target_user_ans, other_ans)
            results.append((uid, sim))

        # Сортируем по убыванию схожести
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def get_question_summary(self, question_index, selected_options):
        """Возвращает текстовое описание выбранных вариантов"""
        question = self.get_question(question_index)
        if not question:
            return "Вопрос не найден"
        
        options_text = []
        for opt_idx in selected_options:
            if 0 <= opt_idx < len(question['options']):
                options_text.append(question['options'][opt_idx])
        
        if question['type'] == 'single':
            return options_text[0] if options_text else "Не выбран"
        else:
            return ", ".join(options_text) if options_text else "Не выбрано"

# Можно оставить тестовый код или удалить
if __name__ == "__main__":
    engine = TestEngine()
    print(f"✅ Тестовый движок загружен: {engine.get_total_questions()} вопросов")