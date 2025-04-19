from telegram_bot.store import store

# Supported locales
LANGUAGES = {"en": "English", "uk": "Українська"}

# Translation catalog
MESSAGES = {
    "en": {
        "start_authorized": "You are already authorized. Please choose an action:",
        "start_unauth": "Welcome! Please /authorize to begin.",
        "ask_chat_query": "Please enter the name or ID of the chat you want to analyze:",
        "no_chats_found": "No chats found matching your query. Please try again or /cancel to stop.",
        "select_chat": "I found the following chats. Please select one:",
        "cancel_analyze": "Chat analysis canceled.",
        "lang_changed": "Language changed.",
        "choose_language": "Select your language:",
        "help_text": (
            "Available actions:\n"
            "- /summary: Get unread messages summary\n"
            "- /analyze: Analyze a specific chat\n"
            "- Mark as Read: Mark chats as read\n"
            "- /help: Display this help information\n"
            "- /language: Change bot language"
        ),
        "prompt_unread_question": "What did I miss?",
        "no_unread_chats_found": "No unread chats found.",
        "ask_mark_read": "Would you like to mark messages as read?",
        "analyze_given_chat": "Analyze given chat",
        "no_chat_selected": "No chat selected for analysis.",
        "mark_unread_as_read": "Marking unread messages as read.",
        "done": "Done!",
        "selected_chat_info": "Selected chat: {name} (ID: {id})",
        "understood": "Understood!",
        # Authorization/Login related
        "ask_contact": "Please share your contact to authorize. This will provide your phone number securely.",
        "no_contact_received": "No contact received. Please try /authorize again.",
        "invalid_phone_number": "Invalid phone number. Please try /authorize again.",
        "too_many_attempts_wait": "Too many attempts. Please wait {seconds} seconds and try again.",
        "authorization_error": "Authorization error: {error}",
        "numeric_code_prompt": "Please send a numeric code. Add {obf} to the Telegram code and try again.",
        "auth_successful": "Authorization successful!",
        "code_expired": "The code has expired. Use /resend to get a new code or /cancel to stop.",
        "enter_2fa_password": "Two-factor authentication enabled. Please enter your password:",
        "invalid_code_or_error": "Invalid code or error: {error}. Ensure you added {obf} to the Telegram code. Use /resend for a new code or /cancel to stop.",
        "auth_successful_2fa": "Authorization successful with 2FA!",
        "invalid_password_or_error": "Invalid password or error: {error}. Please try again or use /cancel to stop.",
        "auth_error_msg": "No active authorization session. Please start with /authorize.",
        "code_resent_info": "A new code was sent to {phone_number}. Add {obf} to it and enter the modified code within 2 minutes.",
        "resend_code_error": "Error resending code: {error}. Try /authorize again.",
        "cancelled_process": "Cancelled process",
        "logout_success": "You have been logged out.",
        "logout_not_logged_in": "You are not logged in.",
        "code_sent_instructions": (
            "Contact received! Telegram sent a code to {phone_number}. "
            "To send it securely, add {obf} to the code (e.g., if the code is 12345, send {example}). "
            "Enter the modified code within 2 minutes. Use /resend if it expires."
        ),
        # Button labels
        "action_mark_as_read": "Mark as Read",
        "chats_to_select_from": "Found chats for the given query:\n\n{chats}",
    },
    "uk": {
        "start_authorized": "Ви вже авторизовані. Будь ласка, оберіть дію:",
        "start_unauth": "Ласкаво просимо! Будь ласка, /authorize для початку.",
        "ask_chat_query": "Введіть назву або ID чату для аналізу:",
        "no_chats_found": "Чати за запитом не знайдено. Спробуйте ще раз або /cancel для скасування.",
        "select_chat": "Знайдено такі чати. Будь ласка, оберіть один:",
        "cancel_analyze": "Аналіз чату скасовано.",
        "lang_changed": "Мову змінено.",
        "choose_language": "Оберіть мову:",
        "help_text": (
            "Доступні дії:\n"
            "- /summary: Отримати резюме непрочитаних повідомлень\n"
            "- /analyze: Аналіз конкретного чату\n"
            "- Mark as Read: Відмітити чати як прочитані\n"
            "- /help: Показати довідку\n"
            "- /language: Змінити мову бота"
        ),
        "prompt_unread_question": "Що я пропустив?",
        "no_unread_chats_found": "Немає непрочитаних чатів.",
        "ask_mark_read": "Бажаєте позначити повідомлення як прочитані?",
        "analyze_given_chat": "Аналізувати вказаний чат",
        "no_chat_selected": "Чат для аналізу не обрано.",
        "mark_unread_as_read": "Позначаю непрочитані повідомлення як прочитані.",
        "done": "Готово!",
        "selected_chat_info": "Обраний чат: {name} (ID: {id})",
        "understood": "Зрозуміло!",
        # Authorization/Login related
        "ask_contact": "Будь ласка, надішліть свій контакт для авторизації. Це безпечно передасть ваш номер телефону.",
        "no_contact_received": "Контакт не отримано. Будь ласка, спробуйте /authorize ще раз.",
        "invalid_phone_number": "Некоректний номер телефону. Будь ласка, спробуйте /authorize ще раз.",
        "too_many_attempts_wait": "Забагато спроб. Будь ласка, зачекайте {seconds} секунд і спробуйте знову.",
        "authorization_error": "Помилка авторизації: {error}",
        "numeric_code_prompt": "Будь ласка, надішліть числовий код. Додайте {obf} до коду Telegram і спробуйте ще раз.",
        "auth_successful": "Авторизація успішна!",
        "code_expired": "Код протерміновано. Використайте /resend для отримання нового коду або /cancel для зупинки.",
        "enter_2fa_password": "Увімкнено двофакторну автентифікацію. Будь ласка, введіть свій пароль:",
        "invalid_code_or_error": "Некоректний код або помилка: {error}. Переконайтеся, що ви додали {obf} до коду Telegram. Використайте /resend для нового коду або /cancel для зупинки.",
        "auth_successful_2fa": "Авторизація з 2FA успішна!",
        "invalid_password_or_error": "Некоректний пароль або помилка: {error}. Будь ласка, спробуйте ще раз або використайте /cancel для зупинки.",
        "auth_error_msg": "Немає активної сесії авторизації. Будь ласка, почніть з /authorize.",
        "code_resent_info": "Новий код було надіслано на {phone_number}. Додайте {obf} до нього та введіть змінений код протягом 2 хвилин.",
        "resend_code_error": "Помилка надсилання коду: {error}. Спробуйте /authorize ще раз.",
        "cancelled_process": "Процес скасовано.",
        "logout_success": "Ви успішно вийшли з системи.",
        "logout_not_logged_in": "Ви не увійшли в систему.",
        "code_sent_instructions": (
            "Контакт отримано! Telegram надіслав код на {phone_number}. "
            "Щоб відправити його безпечно, додайте {obf} до коду (наприклад, якщо код 12345, надішліть {example}). "
            "Введіть змінений код протягом 2 хвилин. Використайте /resend, якщо код протерміновано."
        ),
        # Button labels
        "action_mark_as_read": "Відмітити як прочитане",
        "chats_to_select_from": "Знайдені чати за запитом:\n\n{chats}",
    },
}

def get_locale(user_id: str) -> str:
    loc = store.get(f"lang:{user_id}")
    return loc or "uk"

def t(user_id: str, key: str) -> str:
    lang = get_locale(user_id)
    return MESSAGES.get(lang, MESSAGES["uk"]).get(key, key)