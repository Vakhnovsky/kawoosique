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
    
    # Извлекаем имя папки поста для формирования путей в Page Bundles (например, '20260619-test-phone')
    post_slug = os.path.basename(os.path.dirname(file_path))
    
    # 1. Автоматическая трансформация путей стандартных картинок: ![alt](phone.jpg) или ![alt](/images/knife.jpg)
    def repl_standard_image(match):
        alt = match.group(1)
        img_path = match.group(2)
        if img_path.startswith(("http://", "https://")):
            return match.group(0)
        elif img_path.startswith("/"):
            # Старые глобальные картинки от корня
            return f"![{alt}]({DOMAIN}{img_path})"
        else:
            # Относительные картинки внутри Page Bundles
            clean_path = img_path
            if clean_path.startswith("./"):
                clean_path = clean_path[2:]
            clean_path = clean_path.lstrip("/")
            return f"![{alt}]({DOMAIN}/posts/{post_slug}/{clean_path})"

    content = re.sub(r"!\[(.*?)\]\((.*?)\)", repl_standard_image, content)

    # 2. Автоматическая трансформация Obsidian-картинок: ![[phone.jpg]] или ![[phone.jpg|300]]
    def repl_obsidian_image(match):
        inner = match.group(1)
        # Отсекаем параметры ширины (например, |300)
        clean_name = inner.split("|")[0].strip()
        if clean_name.startswith(("http://", "https://")):
            return f"![изображение]({clean_name})"
        elif clean_name.startswith("/"):
            return f"![изображение]({DOMAIN}{clean_name})"
        else:
            if clean_name.startswith("./"):
                clean_name = clean_name[2:]
            clean_name = clean_name.lstrip("/")
            return f"![изображение]({DOMAIN}/posts/{post_slug}/{clean_name})"

    content = re.sub(r"!\[\[(.*?)\]\]", repl_obsidian_image, content)

    # 3. Преобразуем обычные внутренние ссылки (начинающиеся с /), делая их абсолютными
    def repl_standard_link(match):
        text = match.group(1)
        link_path = match.group(2)
        if link_path.startswith("/") and not link_path.startswith("//"):
            return f"[{text}]({DOMAIN}{link_path})"
        return match.group(0)

    content = re.sub(r"\[(.*?)\]\((.*?)\)", repl_standard_link, content)
    
    # 4. Фикс одиночных переносов строк из Obsidian (Спецификация GFM Markdown)
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

    # 5. Интеграция Instant View
    iv_link = f"https://t.me/iv?url={DOMAIN}/posts/{post_slug}/&rhash={RHASH}"
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
    
    # Сначала проверяем аргументы командной строки
    if len(sys.argv) >= 2:
        target_file = sys.argv[1]
    else:
        # Если аргументов нет, пробуем получить из переменной окружения GitHub Actions
        target_file = os.getenv("TARGET_MD_FILE")
        
    # Защита от пустых запусков (например, если TARGET_MD_FILE пустой из-за отсутствия изменений постов)
    if not target_file or target_file.strip() == "":
        print("Предупреждение: Файл для публикации не обнаружен (целевой путь пуст). Пропускаем шаг публикации.")
        sys.exit(0)
        
    asyncio.run(main(target_file))