import os
import sys
import re
import json
import urllib.request
import yaml

DOMAIN = "https://kawoosique.com"

def escape_markdown_v2(text):
    """
    Экранирует спецсимволы для Telegram MarkdownV2.
    Символы: _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
    Особенно критично экранировать '.', '-', '#' и '!', так как они часто встречаются в тексте.
    """
    # Список всех символов, которые ТГ требует экранировать
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    
    # Сначала временно сохраним ссылки, чтобы не поломать их синтаксис при экранировании
    # Ищем конструкции [текст](ссылка)
    links = []
    def save_link(match):
        links.append(match.group(0))
        return f"__LINK_PLACEHOLDER_{len(links)-1}__"
    
    # Прячем ссылки
    text_hidden = re.sub(r'\[.*?\]\(.*?\)', save_link, text)
    
    # Теперь экранируем ВСЕ опасные символы в оставшемся тексте
    escaped_text = ""
    for char in text_hidden:
        if char in escape_chars:
            escaped_text += f"\\{char}"
        else:
            escaped_text += char
            
    # Возвращаем ссылки на место, но внутри самой ссылки (в URL) тоже нужно заэкранировать 
    # символы вроде точек или дефисов, если они там есть, кроме скобок и самого каркаса.
    # Для простоты: в скрытых ссылках мы уже имеем готовые валидные URL, 
    # но ТГ требует экранировать дефисы и точки даже внутри URL в MarkdownV2!
    for i, link in enumerate(links):
        # Разбираем скрытую ссылку на [текст] и (url)
        link_match = re.match(r'\[(.*?)\]\((.*?)\)', link)
        if link_match:
            link_text = link_match.group(1)
            link_url = link_match.group(2)
            
            # Экранируем текст внутри ссылки
            escaped_ltext = ""
            for char in link_text:
                if char in escape_chars:
                    escaped_ltext += f"\\{char}"
                else:
                    escaped_ltext += char
            
            # В URL экранируем только самые критичные для ТГ символы: . - ) ( и т.д.
            escaped_lurl = ""
            for char in link_url:
                if char in escape_chars:
                    escaped_lurl += f"\\{char}"
                else:
                    escaped_lurl += char
            
            # Собираем обратно БЕЗ экранирования внешних скобок разметки
            valid_tg_link = f"[{escaped_ltext}]({escaped_lurl})"
            escaped_text = escaped_text.replace(f"__LINK_PLACEHOLDER_{i}__", valid_tg_link)
            
    return escaped_text

def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    target_file = os.environ.get("TARGET_MD_FILE")
    
    if not bot_token or not channel_id:
        print("Ошибка: Не настроены токены TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID.")
        sys.exit(1)
        
    if not target_file:
        print("В текущем коммите нет измененных файлов в content/posts/. Пропускаем запуск.")
        return

    if not os.path.exists(target_file):
        print(f"Ошибка: Файл {target_file} не найден в репозитории.")
        sys.exit(1)

    print(f"Обработка файла: {target_file}")
    
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Парсим Front Matter
    meta_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not meta_match:
        print("Файл не содержит разметку Front Matter (---).")
        return
        
    front_matter_raw = meta_match.group(1)
    post_body = meta_match.group(2).strip()
    
    try:
        meta = yaml.safe_load(front_matter_raw)
    except Exception as e:
        print(f"Ошибка YAML: {e}")
        sys.exit(1)
        
    title = meta.get("title", "Новая публикация")
    
    # Сборка ссылки на обложку
    cover_url = None
    if "cover" in meta and isinstance(meta["cover"], dict):
        cover_img = meta["cover"].get("image")
        if cover_img:
            cover_url = f"{DOMAIN}{cover_img}" if cover_img.startswith("/") else f"{DOMAIN}/{cover_img}"

    # Переводим относительные пути картинок в абсолютные веб-ссылки ДО экранирования
    post_body = re.sub(r'\!\[(.*?)\]\((/images/.*?)\)', f'![\\1]({DOMAIN}\\2)', post_body)
    
    # Картинка-превью (если есть) оформляется как невидимая ссылка в начале
    prefix = ""
    if cover_url:
        # Для невидимой ссылки используем специальный символ пустого пространства
        prefix = f"[ ]({cover_url})"
    
    # Формируем финальное сообщение: заголовок делаем жирным вручную
    # Важно: сначала экранируем чистый заголовок и чистое тело
    safe_title = escape_markdown_v2(title)
    safe_body = escape_markdown_v2(post_body)
    
    # Собираем всё вместе. Конструкцию жирности `*...*` добавляем уже поверх экранированного текста!
    final_text = f"{prefix}*{safe_title}*\n\n{safe_body}"

    # Делаем запрос к официальному Bot API
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": final_text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    print("Отправка сообщения в Telegram через официальный sendMessage MarkdownV2...")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read().decode('utf-8')
            print(f"Успешный ответ от ТГ: {res_data}")
    except urllib.error.HTTPError as e:
        print(f"Ошибка Telegram API (HTTP {e.code}): {e.read().decode('utf-8')}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка сети: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()