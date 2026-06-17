import os
import sys
import re
import asyncio
import yaml
from aiogram import Bot

DOMAIN = "https://kawoosique.com"

async def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    target_file = os.environ.get("TARGET_MD_FILE")
    
    if not bot_token or not channel_id:
        print("Ошибка: Не настроены токены в GitHub Secrets.")
        sys.exit(1)
        
    if not target_file:
        print("Нет файла для обработки.")
        return

    print(f"Проверка файла: {target_file}")
    bot = Bot(token=bot_token)
    
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Отделяем YAML-шапку от текста статьи
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
    
    # Обработка обложки (если есть)
    cover_url = None
    if "cover" in meta and isinstance(meta["cover"], dict):
        cover_img = meta["cover"].get("image")
        if cover_img:
            cover_url = f"{DOMAIN}{cover_img}" if cover_img.startswith("/") else f"{DOMAIN}/{cover_img}"

    # Переводим относительные пути картинок в тексте во внешние абсолютные URL
    post_body = re.sub(r'\!\[(.*?)\]\((/images/.*?)\)', f'![\\1]({DOMAIN}\\2)', post_body)
    
    # Собираем финальный текст сообщения
    final_text = ""
    if cover_url:
        final_text += f"![Обложка]({cover_url})\n\n"
        
    final_text += f"# {title}\n\n" + post_body

    print("Пробуем отправить Rich Message...")
    try:
        await bot.send_rich_message(
            chat_id=channel_id,
            rich_message=final_text,
            formatting_options="rich_markdown"
        )
        print("УРА! Публикация в канале!")
    except Exception as e:
        print(f"Ошибка при отправке: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())