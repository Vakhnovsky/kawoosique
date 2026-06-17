import os
import sys
import re
import json
import urllib.request
import yaml

DOMAIN = "https://kawoosique.com"

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
    
    # Формируем финальное тело для Rich Markdown
    final_text = ""
    if cover_url:
        final_text += f"![Обложка]({cover_url})\n\n"
        
    final_text += f"# {title}\n\n" + post_body

    # Официальный эндпоинт для отправки форматированных Rich-сообщений
    url = f"https://api.telegram.org/bot{bot_token}/sendRichMessage"
    
    # Структура по документации Bot API 10.1 для rich_markdown
    payload = {
        "chat_id": channel_id,
        "rich_message": final_text
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    print("Отправка Rich Message напрямую в Telegram API...")
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