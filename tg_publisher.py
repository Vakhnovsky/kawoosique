import os
import re
import sys
import asyncio
import frontmatter
import aiohttp
from aiogram import Bot
from aiogram.types import InputRichMessage

# Технические константы проекта KAWOOSIQUE
DOMAIN = "https://kawoosique.com"
RHASH = "5dda3eb0d9e2b1"

# Динамическая сборка маркера, чтобы веб-интерфейсы не вырезали его как HTML-комментарий
TG_MARKER = "<!" + "--" + "tg" + "--" + ">"

async def wait_for_url(url: str, timeout: int = 120, delay: int = 5) -> bool:
    """
    Асинхронно ожидает, пока URL обложки станет доступен (вернет HTTP 200).
    Предотвращает гонку условий в GitHub Actions, когда бот отправляет
    пост в Телеграм до того, как Hugo успел завершить деплой сайта.
    """
    if not url.startswith("http"):
        return False
        
    print(f"Ожидание публикации обложки на сервере: {url}")
    start_time = asyncio.get_event_loop().time()
    
    async with aiohttp.ClientSession() as session:
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                async with session.head(url, timeout=5) as response:
                    if response.status == 200:
                        print("Успех! Обложка опубликована и доступна для Telegram.")
                        return True
            except Exception:
                pass
            await asyncio.sleep(delay)
            
    print("Предупреждение: Превышено время ожидания обложки. Отправляем пост как есть.")
    return False

async def transform_markdown(file_path):
    """
    Парсит Front Matter заметки Obsidian, преобразует относительные пути
    изображений в абсолютные URL сайта и форматирует тело под Rich Markdown.
    Возвращает кортеж (отформатированный_текст, url_обложки).
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

    # 4. Извлекаем и собираем URL обложки (Cover Image)
    cover_data = post.get('cover', {})
    cover_url = ""
    if isinstance(cover_data, dict):
        cover_img = cover_data.get('image', '')
        if cover_img:
            # Очищаем имя от префиксов путей
            cover_img_clean = cover_img.replace("./", "").lstrip("/")
            is_relative = cover_data.get('relative', False)
            if is_relative and is_bundle:
                cover_url = f"{DOMAIN}/posts/{slug}/{cover_img_clean}"
            elif is_relative:
                cover_url = f"{DOMAIN}/images/{cover_img_clean}"
            else:
                cover_url = cover_img if cover_img.startswith("http") else f"{DOMAIN}/{cover_img_clean}"

    # 5. Интеграция Instant View и скрытой обложки
    iv_link = f"https://t.me/iv?url={DOMAIN}/posts/{slug}/&rhash={RHASH}"
    invisible_char = "\u200b" # Гарантированный Юникод-символ нулевой ширины
    
    if tg_mode == 'iv_only':
        text = f"[{invisible_char}]({iv_link})**{title}**\n\n{iv_link}"
    elif tg_mode == 'rich_iv':
        text = f"[{invisible_char}]({iv_link})**{title}**\n\n{content}\n\n[Читать в Instant View]({iv_link})"
    else: # rich_only
        # Бесшовно прикрепляем обложку через невидимый символ-ссылку в начале сообщения для генерации превью
        if cover_url:
            text = f"[{invisible_char}]({cover_url})**{title}**\n\n{content}" if title else f"[{invisible_char}]({cover_url}){content}"
        else:
            text = f"**{title}**\n\n{content}" if title else content
        
    return text, cover_url

async def main(file_path):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHANNEL_ID")
    
    if not bot_token or not channel_id:
        print("Ошибка: Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не заданы.")
        sys.exit(1)
        
    bot = Bot(token=bot_token)
    
    try:
        rich_markdown_text, cover_url = await transform_markdown(file_path)
        
        # Если у нас есть обложка, дожидаемся её физической публикации на сайте
        if cover_url:
            await wait_for_url(cover_url)
        
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