import os
import re
import sys
import asyncio
import frontmatter
from aiogram import Bot
from aiogram.types import InputRichMessage

# Технические константы проекта KAWOOSIQUE
DOMAIN = "https://kawoosique.com"
RHASH = "5dda3eb0d9e2b1"

# Динамическая сборка маркера, чтобы веб-интерфейсы не вырезали его как HTML-комментарий
TG_MARKER = "<!" + "--" + "tg" + "--" + ">"

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
    
    # 1. Интеллектуальное определение слага поста для Page Bundles и плоской структуры
    filename = os.path.basename(file_path)
    if filename == "index.md":
        # Если это Page Bundle (content/posts/folder/index.md) -> берем имя папки
        slug = os.path.basename(os.path.dirname(file_path))
        is_bundle = True
    else:
        # Если это старая плоская структура (content/posts/name.md) -> берем имя файла
        slug = os.path.splitext(filename)[0]
        is_bundle = False
        
    # 2. Автоматическая трансформация путей картинок
    # Сначала обрабатываем глобальные пути, начинающиеся со слэша /
    content = content.replace('](/', f']({DOMAIN}/')
    content = content.replace('="/', f'="{DOMAIN}/')
    
    # Если это Page Bundle, переводим все относительные картинки в абсолютные URL
    if is_bundle:
        # Стандартные Markdown-картинки: ![alt](phone.jpg) или ![alt](./phone.jpg)
        def repl_standard_image(match):
            alt = match.group(1)
            img_path = match.group(2)
            if img_path.startswith(("http://", "https://", "/")):
                return match.group(0) # Пропускаем внешние и глобальные
            clean_path = img_path.lstrip("./")
            return f"![{alt}]({DOMAIN}/posts/{slug}/{clean_path})"

        content = re.sub(r"!\[(.*?)\]\((.*?)\)", repl_standard_image, content)

        # Obsidian Wiki-картинки: ![[phone.jpg]] или ![[phone.jpg|300]]
        def repl_obsidian_image(match):
            inner = match.group(1)
            clean_name = inner.split("|")[0].strip()
            if clean_name.startswith(("http://", "https://", "/")):
                return f"![изображение]({clean_name})"
            clean_path = clean_name.lstrip("./")
            return f"![изображение]({DOMAIN}/posts/{slug}/{clean_path})"

        content = re.sub(r"!\[\[(.*?)\]\]", repl_obsidian_image, content)
    
    # 3. Фикс одиночных переносов строк из Obsidian (Спецификация GFM Markdown)
    blocks = content.split('\n\n')
    processed_blocks = []
    for block in blocks:
        if any(block.startswith(p) for p in ['#', '-', '*', '>', '`', '|']) or '```' in block:
            processed_blocks.append(block)
        else:
            lines = [line.strip() for line in block.splitlines()]
            clean_block = ' '.join([l for l in lines if l])
            processed_blocks.append(clean_block)
    content = '\n\n'.join(processed_blocks)

    # 4. Интеграция Instant View с корректным слагом
    iv_link = f"https://t.me/iv?url={DOMAIN}/posts/{slug}/&rhash={RHASH}"
    invisible_char = "﻿" # Zero Width No-Break Space
    
    if tg_mode == 'iv_only':
        text = f"[{invisible_char}]({iv_link})*{title}*\n\n{iv_link}"
    elif tg_mode == 'rich_iv':
        text = f"[{invisible_char}]({iv_link})*{title}*\n\n{content}\n\n[Читать в Instant View]({iv_link})"
    else: # rich_only
        text = f"*{title}*\n\n{content}" if title else content
        
    return text

async def main(file_path):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHANNEL_ID")
    
    if not bot_token or not channel_id:
        print("Ошибка: Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID (или TELEGRAM_CHANNEL_ID) не заданы.")
        sys.exit(1)
        
    bot = Bot(token=bot_token)
    
    try:
        rich_markdown_text = await transform_markdown(file_path)
        
        if len(rich_markdown_text) > 32768:
            print(f"Предупреждение: Текст превышает лимит API 10.1 ({len(rich_markdown_text)} симв.). Сжатие...")
            rich_markdown_text = rich_markdown_text[:32760] + "\n\n..."
            
        await bot.send_rich_message(
            chat_id=channel_id,
            rich_message=InputRichMessage(markdown=rich_markdown_text)
        )
        print(f"Успех! Пост из файла {file_path} успешно опубликован в Telegram.")
        
    except Exception as e:
        import traceback
        print(f"Критическая ошибка при отправке через sendRichMessage: {e}")
        print("\n=== ПОЛНЫЙ СТЕК ВЫЗОВОВ (TRACEBACK) ===")
        traceback.print_exc()
        print("=======================================\n")
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    target_file = None
    if len(sys.argv) >= 2:
        target_file = sys.argv[1]
        
    # Защита от пустых запусков экшена (если изменился файл темы, а не пост)
    if not target_file or target_file.strip() == "":
        print("Предупреждение: Путь к файлу публикации пуст. Пропускаем.")
        sys.exit(0)
        
    asyncio.run(main(target_file))