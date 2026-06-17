import os
import sys
import re
import json
import urllib.request
import yaml

DOMAIN = "https://kawoosique.com"

def escape_markdown_v2(text):
    """
    Экранирует спецсимволы для Telegram MarkdownV2, 
    но оставляет нетронутыми символы разметки: *, _, `, [, ], (, ), #, -, !
    """
    # Символы, которые нужно экранировать в обычном тексте MarkdownV2
    escape_chars = r'\/{}><%+=.|!'
    # Экранируем их по одному
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    # Отдельно аккуратно экранируем точки и дефисы, если они не являются частью разметки списков
    # Но для надежности базового рендеринга просто заэкранируем отдельно стоящие технические знаки
    text = re.sub(r'([.\\-])', r'\\\1', text)
    return text

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

    # Делаем пути к картинкам внутри текста абсолютными
    post_body = re.sub(r'\!\[(.*?)\]\((/images/.*?)\)', f'![\\1]({DOMAIN}\\2)', post_body)
    
    # Экранируем текст под правила MarkdownV2
    safe_title = escape_markdown_v2(title)
    safe_body = escape_markdown_v2(post_body)
    
    # Формируем финальный текст сообщения
    final_text = ""
    if cover_url:
        safe_cover_url = escape_markdown_v2(cover_url)
        # В MarkdownV2 картинка-превью изящно прячется в невидимый символ перед заголовком
        final_text += f"[ ]({safe_cover_url})"
        
    final_text += f"*{safe_title}*\n\n{safe_body}"

    # Используем ОФИЦИАЛЬНЫЙ и 100% стабильный эндпоинт Telegram Bot API
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": channel_id,
        "text": final_text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False # Чтобы обложка красиво подгружалась
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