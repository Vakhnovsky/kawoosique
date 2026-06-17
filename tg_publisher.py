import os
import sys
import re
import json
import urllib.request
import yaml

DOMAIN = "https://kawoosique.com"

def main():
    # Токены авторизации по-прежнему берем из защищенных секретов
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    target_file = os.environ.get("TARGET_MD_FILE")
    
    if not bot_token or not channel_id:
        print("Ошибка: Не настроены токены в GitHub Secrets.")
        print("Критическая ошибка: Не настроены токены TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID в GitHub Secrets.")
        sys.exit(1)

    # Автономный поиск: скрипт сам сканирует папку постов
    posts_dir = "content/posts"
    if not os.path.exists(posts_dir):
        print(f"Ошибка: Папка с постами {posts_dir} не найдена в репозитории.")
        sys.exit(1)
        
    md_files = [os.path.join(posts_dir, f) for f in os.listdir(posts_dir) if f.endswith(".md")]
    if not md_files:
        print("В папке content/posts/ не найдено ни одного .md файла. Публикация невозможна.")
        return

    # Находим самый свежий файл по времени его модификации (mtime)
    target_file = max(md_files, key=os.path.getmtime)
    print(f"Робот выбрал для публикации самый свежий файл: {target_file}")
    
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Изолируем YAML Front Matter
    meta_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not meta_match:
        print(f"Файл {target_file} пропущен: отсутствует шапка Front Matter.")
        return
        
    front_matter_raw = meta_match.group(1)
    post_body = meta_match.group(2).strip()
    
    try:
        meta = yaml.safe_load(front_matter_raw)
    except Exception as e:
        print(f"Ошибка парсинга YAML: {e}")
        sys.exit(1)
        
    title = meta.get("title", "Новая публикация")
    
    # Сборка ссылки на обложку
    cover_url = None
    if "cover" in meta and isinstance(meta["cover"], dict):
        cover_img = meta["cover"].get("image")
        if cover_img:
            cover_url = f"{DOMAIN}{cover_img}" if cover_img.startswith("/") else f"{DOMAIN}/{cover_img}"

    # Подставляем абсолютный домен к картинкам внутри текста
    post_body = re.sub(r'\!\[(.*?)\]\((/images/.*?)\)', f'![\\1]({DOMAIN}\\2)', post_body)
    
    # Формируем текст
    final_text = ""
    if cover_url:
        final_text += f"![Обложка]({cover_url})\n\n"
        
    final_text += f"# {title}\n\n" + post_body

    # Отправляем текстовый POST запрос напрямую к серверам Telegram
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Раз мы тестируем базу, шлем через стандартный, 100% рабочий метод sendMessage с parse_mode
    payload = {
        "chat_id": channel_id,
        "text": final_text,
        "parse_mode": "Markdown" # Базовый маркдаун для проверки доставки
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    print(f"Отправка запроса в Telegram для канала {channel_id}...")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read().decode('utf-8')
            print(f"Ответ шлюза Telegram: {res_data}")
    except urllib.error.HTTPError as e:
        print(f"Ошибка шлюза Telegram (HTTP {e.code}): {e.read().decode('utf-8')}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка сети: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()