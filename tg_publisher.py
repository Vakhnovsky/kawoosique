import os
import sys
import re
import asyncio
import yaml
from aiogram import Bot

# Глобальные настройки твоего проекта
DOMAIN = "https://kawoosique.com"
RHASH = "5dda3eb0d9e2b1"

async def main():
    # 1. Безопасный сбор учетных данных из GitHub Secrets
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    target_file = os.environ.get("TARGET_MD_FILE")
    
    if not bot_token or not channel_id:
        print("Критическая ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не настроены в репозитории.")
        sys.exit(1)
        
    if not target_file:
        print("В текущем коммите нет измененных или новых заметок в папке content/posts/. Пропускаем шаг публикации.")
        return

    if not os.path.exists(target_file):
        print(f"Ошибка: Указанный файл {target_file} физически не найден в репозитории.")
        sys.exit(1)
        
    print(f"Начинается обработка целевого файла: {target_file}")
    bot = Bot(token=bot_token)
    
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 2. Изолируем YAML Front Matter от тела заметки
    meta_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not meta_match:
        print(f"Файл {target_file} пропущен: отсутствует стандартная разметка Front Matter (---).")
        return
        
    front_matter_raw = meta_match.group(1)
    post_body = meta_match.group(2).strip()
    
    try:
        meta = yaml.safe_load(front_matter_raw)
    except Exception as e:
        print(f"Критическая ошибка парсинга YAML-шапки заметки: {e}")
        sys.exit(1)
        
    title = meta.get("title", "Новая публикация")
    tg_mode = meta.get("tg_mode", "rich_only") # По умолчанию публикуем чистый Rich-формат
    
    # Вычисляем slug для веб-версии и Instant View (имя файла без расширения)
    slug = os.path.splitext(os.path.basename(target_file))[0]
    site_url = f"{DOMAIN}/posts/{slug}/"
    iv_url = f"https://t.me/iv?url={site_url}&rhash={RHASH}"
    
    # 3. Интеллектуальный парсинг обложки (если она задана)
    cover_url = None
    if "cover" in meta and isinstance(meta["cover"], dict):
        cover_img = meta["cover"].get("image")
        if cover_img:
            if cover_img.startswith("/"):
                cover_url = f"{DOMAIN}{cover_img}"
            else:
                cover_url = f"{DOMAIN}/{cover_img}"

    # 4. Обработка контента под выбранный сценарий (tg_mode)
    if tg_mode == "iv_only":
        print("Режим [iv_only]: Формируется короткая карточка со ссылкой на Instant View.")
        final_text = f"# {title}\n\n[⚡ Читать в Instant View]({iv_url})"
        
    else:
        # Сценарий hybrid: Отсекаем хвост лонгрида по маркеру комментария или старому ---tg---
        if tg_mode == "hybrid":
            print("Режим [hybrid]: Вырезаем превью по маркеру.")
            if "" in post_body:
                post_body = post_body.split("")[0].strip()
            elif "---tg---" in post_body:
                post_body = post_body.split("---tg---")[0].strip()
            else:
                print("Предупреждение: Маркер разделения не найден. Текст отправится целиком.")
        else:
            print("Режим [rich_only]: Текст подготавливается к публикации целиком.")

        # Превращаем относительные пути Obsidian/Hugo вида ![alt](/images/foto.jpg) в абсолютные адреса
        post_body = re.sub(r'\!\[(.*?)\]\((/images/.*?)\)', f'![\\1]({DOMAIN}\\2)', post_body)
        
        # Собираем финальное сообщение
        final_text = ""
        
        # Если есть обложка, нативно вшиваем её первой строкой
        if cover_url:
            final_text += f"![Обложка]({cover_url})\n\n"
            
        final_text += f"# {title}\n\n" + post_body
        
        # Если это гибридный режим — пристыковываем ссылку на IV лонгрида в самый конец
        if tg_mode == "hybrid":
            final_text += f"\n\n[⚡ Читать статью целиком в Instant View]({iv_url})"

    # 5. Стреляем в Bot API 10.1 через метод send_rich_message (исправлен аргумент на rich_message)
    print(f"Отправка Rich-сообщения в канал в режиме: {tg_mode}")
    try:
        await bot.send_rich_message(
            chat_id=channel_id,
            rich_message=final_text, # aiogram 3.29.0+ требует именно этот параметр вместо text
            formatting_options="rich_markdown"
        )
        print("Публикация успешно размещена в канале!")
    except Exception as e:
        print(f"Критическая ошибка отправки через метод sendRichMessage: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())