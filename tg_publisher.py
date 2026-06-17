import os
import sys
import asyncio
import frontmatter
from aiogram import Bot
from aiogram.types import InputRichMessage

# Технические константы проекта KAWOOSIQUE
DOMAIN = "https://kawoosique.com"
RHASH = "5dda3eb0d9e2b1"

async def transform_markdown(file_path):
    """
    Парсит Front Matter заметки Obsidian, преобразует относительные пути
    изображений в абсолютные URL сайта и форматирует тело под Rich Markdown.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        post = frontmatter.load(f)
        
    title = post.get('title', '')
    tg_mode = post.get('tg_mode', 'rich_only')
    content = post.content
    
    # 1. Автоматическая трансформация путей картинок: /images/X.jpg -> https://kawoosique.com/images/X.jpg
    content = content.replace('](/', f']({DOMAIN}/')
    content = content.replace('="/', f'="{DOMAIN}/')
    
    # 2. Извлечение и валидация обложки (cover.image) из Front Matter
    cover_data = post.get('cover', {})
    cover_url = ""
    if isinstance(cover_data, dict):
        cover_image = cover_data.get('image', '')
        if cover_image:
            if not cover_image.startswith('http'):
                cover_url = f"{DOMAIN}{cover_image}" if cover_image.startswith('/') else f"{DOMAIN}/{cover_image}"
            else:
                cover_url = cover_image

    # 3. Формирование ссылки на Instant View
    slug = post.get('slug', os.path.splitext(os.path.basename(file_path))[0])
    iv_url = f"https://t.me/iv?url={DOMAIN}/posts/{slug}/&rhash={RHASH}"
    
    # Автоопределение гибридного режима: если есть маркер резака, включаем hybrid автоматически
    if '' in content and tg_mode == 'rich_only':
        tg_mode = 'hybrid'
        
    # 4. Обработка режимов публикации
    if tg_mode == 'hybrid':
        if '' in content:
            body = content.split('')[0].strip()
        else:
            body = content.strip()
        body += f"\n\n[Читать полную версию статьи в Instant View]({iv_url})"
        
    elif tg_mode == 'iv_only':
        description = post.get('description', '')
        body = f"### {title}\n\n{description}\n\n[Открыть Instant View]({iv_url})"
        
    else:  # rich_only (публикация текста целиком в рамках 32k символов)
        body = content.strip()
        
    # 5. Интеграция обложки в начало сообщения (Rich Markdown нативно поддерживает блоки картинок)
    if cover_url and tg_mode != 'iv_only':
        body = f"![Обложка]({cover_url})\n\n" + body
        
    # 6. Добавление нативного заголовка H1, если его нет в начале текста
    if title and not body.startswith(f"# {title}") and tg_mode != 'iv_only':
        body = f"# {title}\n\n" + body
        
    return body

async def main(file_path):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    
    if not bot_token or not channel_id:
        print("Ошибка: Переменные окружения TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы в GitHub Secrets.")
        sys.exit(1)
        
    bot = Bot(token=bot_token)
    
    try:
        # Получаем очищенный и размеченный текст
        rich_markdown_text = await transform_markdown(file_path)
        
        # Контроль жесткого лимита Bot API 10.1 (32 768 символов UTF-8)
        if len(rich_markdown_text) > 32768:
            print(f"Предупреждение: Текст превышает лимит API 10.1 ({len(rich_markdown_text)} симв.). Сжатие...")
            rich_markdown_text = rich_markdown_text[:32760] + "\n\n..."
            
        # Отправка структурированного Rich-сообщения
        await bot.send_rich_message(
            chat_id=channel_id,
            rich_message=InputRichMessage(markdown=rich_markdown_text)
        )
        print(f"Успех! Пост из файла {file_path} успешно опубликован в Telegram.")
        
    except Exception as e:
        print(f"Критическая ошибка при отправке через sendRichMessage: {e}")
        sys.exit(1)
    finally:
        # Корректно закрываем сессию aiogram
        await bot.session.close()

if __name__ == "__main__":
    target_file = None
    
    # 1. Сначала проверяем аргументы командной строки (если запускаем вручную)
    if len(sys.argv) >= 2:
        target_file = sys.argv[1]
        
    # 2. Если аргументов нет, берём из переменной окружения GitHub Actions
    elif os.getenv("TARGET_MD_FILE"):
        target_file = os.getenv("TARGET_MD_FILE")
        
    # 3. Если файла вообще нигде нет — прерываемся с понятной ошибкой
    if not target_file or target_file.strip() == "":
        print("Ошибка запуска: Путь к файлу не передан ни через аргументы, ни через env-переменную TARGET_MD_FILE.")
        sys.exit(1)
        
    print(f"Запуск публикации для файла: {target_file}")
    asyncio.run(main(target_file))