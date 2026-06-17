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
        print("Ошибка: Не настроены токены в GitHub Secrets.")
        sys.exit(1)
        
    if not target_file:
        print("Нет файла для обработки.")
        return

    print(f"Парсинг файла: {target_file}")
    
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    meta_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not meta_match:
        print("Файл не содержит Front Matter.")
        return
        
    front_matter_raw = meta_match.group(1)
    post_body = meta_match.group(2).strip()
    
    try:
        meta = yaml.safe_load(front_matter_raw)
    except Exception as e:
        print(f"Ошибка YAML: {e}")
        sys.exit(1)
        
    title = meta.get("title", "Новая публикация")
    
    # Сборка картинок
    cover_url = None
    if "cover" in meta and isinstance(meta["cover"], dict):
        cover_img = meta["cover"].get("image")
        if cover_img:
            cover_url = f"{DOMAIN}{cover_img}" if cover_img.startswith("/") else f"{DOMAIN}/{cover_img}"

    post_body = re.sub(r'\!\[(.*?)\]\((/images/.*?)\)', f'![\\1]({DOMAIN}\\2)', post_body)
    
    # Формируем финальный текст в формате rich_markdown
    final_text = ""
    if cover_url:
        final_text += f"![Обложка]({cover_url})\n\n"
        
    final_text += f"# {title}\n\n" + post_body

    # Прямой POST запрос к Telegram Bot API без библиотек-посредников
    url = f"https://api.telegram.org/bot{bot_token}/sendRichMessage"
    
    # Согласно Bot API 10.1, метод принимает объект rich_message 
    # Мы передаем строку с разметкой и указываем parse_mode или специализированный тип
    payload = {
        "chat_id": channel_id,
        "rich_message": {
            "text": final_text,
            "parse_mode": "MarkdownV2" # или специализированный флаг rich_markdown, если шлем объектом
        }
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    print("Отправка прямого запроса в Telegram...")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read().decode('utf-8')
            print(f"Ответ от Telegram API: {res_data}")
    except urllib.error.HTTPError as e:
        print(f"Критическая ошибка Telegram API (HTTP {e.code}): {e.read().decode('utf-8')}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка выполнения запроса: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()