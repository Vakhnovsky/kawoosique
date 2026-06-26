import os
import sys
import asyncio
import frontmatter
import re
from aiogram import Bot
from aiogram.types import InputRichMessage

# Технические константы проекта KAWOOSIQUE
DOMAIN = "https://kawoosique.com"
RHASH = "5dda3eb0d9e2b1"

# Служебный маркер для Instant View
TG_MARKER = "<!--tg-->"

async def transform_markdown(file_path):
    """
    Парсит Front Matter заметки Obsidian, преобразует относительные пути
    изображений в абсолютные URL сайта с учетом структуры Page Bundles
    и форматирует тело под Rich Markdown для Telegram API 10.1.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        post = frontmatter.load(f)
        
    title = post.get('title', '')
    tg_mode = post.get('tg_mode', 'rich_only')
    content = post.content
    
    # Вычисляем директорию поста относительно content/ для Page Bundles
    norm_path = os.path.normpath(file_path).replace("\\", "/")
    if norm_path.startswith("content/"):
        norm_path = norm_path[len("content/"):]
    dirname = os.path.dirname(norm_path)  # Например: "posts/20260619-test-phone"
    
    def make_url_absolute(url_path):
        """Преобразует любой локальный путь к файлу в полный URL на сайте."""
        url_path = url_path.strip()
        # Если это уже полная ссылка, e-mail или якорь, не трогаем её
        if url_path.startswith(('http://', 'https://', 'mailto:', 'tel:', '#')):
            return url_path
        # Если ссылка начинается со слэша, она идет от корня сайта (старая логика static/images)
        if url_path.startswith('/'):
            return f"{DOMAIN}{url_path}"
        # Иначе ссылка относительная (новая логика Page Bundles)
        if dirname:
            return f"{DOMAIN}/{dirname}/{url_path}"
        return f"{DOMAIN}/{url_path}"
        
    # 1. Автоматическая трансформация всех относительных/абсолютных изображений и ссылок в тексте поста
    # Картинки: ![alt](url)
    content = re.sub(r'!\[(.*?)\]\((.*?)\)', lambda m: f"![{m.group(1)}]({make_url_absolute(m.group(2))})", content)
    # Обычные ссылки (исключаем картинки через negative lookbehind): [text](url)
    content = re.sub(r'(?<!!)\[(.*?)\]\((.*?)\)', lambda m: f"[{m.group(1)}]({make_url_absolute(m.group(2))})", content)
    # HTML-атрибуты картинок src="..."
    content = re.sub(r'src=["\'](.*?)["\']', lambda m: f'src="{make_url_absolute(m.group(1))}"', content)
    
    # 2. Фикс одиночных переносов строк из Obsidian (Спецификация GFM Markdown)
    # Предотвращает склеивание строк в Telegram при мягких переносах.
    lines = content.split('\n')
    for i in range(len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        # Пропускаем списки, заголовки, блоки цитат, таблиц и кода
        if line.startswith(('-', '*', '+', '#', '>', '|', '```')) or (line[0].isdigit() and line[1:3] == '. '):
            continue
        if i + 1 < len(lines):
            next_line = lines[i+1].strip()
            if next_line and not next_line.startswith(('-', '*', '+', '#', '>', '|', '```')) and not (next_line[0].isdigit() and next_line[1:3] == '. '):
                lines[i] = lines[i] + "  "  # Добавляем два пробела в конце строки по спецификации Markdown
    content = '\n'.join(lines)

    # 3. Извлечение и валидация обложки (cover.image) из Front Matter
    cover_data = post.get('cover', {})
    cover_url = ""
    if isinstance(cover_data, dict):
        cover_image = cover_data.get('image', '')
        if cover_image:
            cover_url = make_url_absolute(cover_image)

    # 4. Формирование тела сообщения
    body = content.strip()
    
    # Вычисляем слаг поста для сборки Instant View ссылки
    if "index.md" in file_path:
        post_slug = os.path.basename(os.path.dirname(file_path))
    else:
        post_slug = os.path.splitext(os.path.basename(file_path))[0]
        
    iv_link = f"https://t.me/iv?url={DOMAIN}/posts/{post_slug}/&rhash={RHASH}"

    # 5. Сборка сообщения в зависимости от режима публикации (tg_mode)
    if tg_mode == 'iv_only':
        # Отправляем только нативный красивый заголовок со ссылкой на Instant View
        body = f"# [{title}]({iv_link})"
    else:
        # Нативно встраиваем обложку в самое начало текста
        if cover_url:
            body = f"![Обложка]({cover_url})\n\n" + body
            
        # Добавляем нативный заголовок H1 (Telegram API 10.1 отрендерит его крупно и жирно)
        if title and not body.startswith(f"# "):
            body = f"# {title}\n\n" + body
            
        # Добавляем ссылку Instant View в конец для гибридного режима
        if tg_mode == 'hybrid':
            body += f"\n\n[Читать в Instant View]({iv_link})"
            
    # Добавляем невидимый HTML-комментарий для связки с IV правилами
    body = TG_MARKER + "\n" + body
    
    return body

async def main():
    if len(sys.argv) < 2:
        print("Использование: python tg_publisher.py <путь_к_файлу.md>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Ошибка: Файл {file_path} не найден.")
        sys.exit(1)
        
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    
    if not bot_token or not channel_id:
        print("Ошибка: TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы в GitHub Secrets.")
        sys.exit(1)
        
    bot = Bot(token=bot_token)
    
    try:
        rich_markdown_text = await transform_markdown(file_path)
        
        # Защитный лимит на размер сообщения в Telegram
        if len(rich_markdown_text) > 32768:
            print(f"Предупреждение: Текст превышает лимит API ({len(rich_markdown_text)} симв.). Сжатие...")
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
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())