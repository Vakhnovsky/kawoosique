import os
import sys
import asyncio
import re
import yaml
from pathlib import Path
from aiogram import Bot

def safe_split_markdown(text, max_size=4000):
    """
    Безопасно режет текст по строкам/абзацам под лимиты Telegram,
    чтобы гарантированно не разрезать markdown-ссылки на картинки.
    """
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    lines = text.split('\n')
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            # Если одна строка (например, таблица) гигантская
            if len(line) > max_size:
                for i in range(0, len(line), max_size):
                    chunks.append(line[i:i+max_size])
            else:
                current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
            
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

async def main():
    # Задержка для гарантированного обновления указателей веток на GitHub
    await asyncio.sleep(3)

    if len(sys.argv) < 2:
        print("Использование: python tg_publisher.py <путь_к_файлу.md>")
        sys.exit(1)

    file_path = sys.argv[1]
    path = Path(file_path)
    if not path.exists():
        print(f"Ошибка: Файл {file_path} не найден.")
        sys.exit(1)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not bot_token or not channel_id or not repo:
        print("Ошибка: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID или GITHUB_REPOSITORY не заданы.")
        sys.exit(1)

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}")
        sys.exit(1)

    # Чистое извлечение Front Matter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        fm_raw = fm_match.group(1)
        body = fm_match.group(2)
        try:
            metadata = yaml.safe_load(fm_raw) or {}
        except Exception as e:
            print(f"Ошибка парсинга YAML: {e}")
            metadata = {}
    else:
        metadata = {}
        body = content

    # Проверка активности публикации
    if not metadata.get('tg_publish', True):
        print("tg_publish установлен в false. Пропускаем публикацию.")
        sys.exit(0)

    # Вычисляем относительный путь папки поста от корня репозитория для Raw-ссылок
    try:
        rel_dir = path.parent.resolve().relative_to(Path(os.getcwd()).resolve())
        post_dir_path = str(rel_dir).replace("\\", "/")
    except Exception:
        post_dir_path = str(path.parent).replace("\\", "/")

    base_url = f"https://raw.githubusercontent.com/{repo}/main/{post_dir_path}"

    # 1. Трансформация стандартных картинок ![alt](image.png) в прямые Raw-ссылки GitHub
    def replace_std(match):
        alt = match.group(1)
        img = match.group(2)
        if img.startswith(('http://', 'https://')):
            return match.group(0)
        img_name = os.path.basename(img)
        return f"![{alt}]({base_url}/{img_name})"

    body = re.sub(r'!\\[(.*?)\\]\\((.*?)\\)', replace_std, body)

    # 2. Трансформация Obsidian wikilinks ![[image.png]] в Standard Markdown под API 10.1
    def replace_wiki(match):
        inner = match.group(1)
        parts = inner.split('|')
        img_name = parts[0].strip()
        # По ТЗ подставляем стандартный синтаксис, который API 10.1 отрендерит нативно
        return f"![Изображение]({base_url}/{img_name})"

    body = re.sub(r'!\\[\\[(.*?)\\]\\]', replace_wiki, body)

    # Парсинг и сборка хэштегов в конец поста
    tags_list = metadata.get('tags', [])
    formatted_tags = ""
    if tags_list and isinstance(tags_list, list):
        tags = []
        for t in tags_list:
            clean_tag = re.sub(r'[^\w\d_]', '', str(t).replace(' ', '_'))
            if clean_tag:
                tags.append(f"#{clean_tag}")
        if tags:
            formatted_tags = "\n\n" + " ".join(tags)

    title = metadata.get('title', '')
    # В API 10.1 решетка # нативно создает жирный крупный H1 заголовок
    header = f"# {title}\n\n" if title else ""
    final_text = f"{header}{body.strip()}{formatted_tags}"

    # Определение и умный поиск локального пути к обложке (Page Bundle или static)
    cover_data = metadata.get('cover', {})
    cover_filename = cover_data.get('image') if isinstance(cover_data, dict) else cover_data

    cover_path = None
    if cover_filename:
        clean_cover = cover_filename.lstrip('/')
        # Проверяем: в папке с постом, в корневой static/ или от текущего рабочего каталога
        paths_to_check = [
            path.parent / os.path.basename(clean_cover),
            Path(os.getcwd()) / "static" / clean_cover,
            Path(os.getcwd()) / clean_cover
        ]
        for p in paths_to_check:
            if p.exists() and p.is_file():
                cover_path = p
                break

        if not cover_path:
            print(f"Предупреждение: Файл обложки {cover_filename} не найден локально. Пост уйдет без превью.")

    bot = Bot(token=bot_token)

    try:
        # Нарезаем контент на безопасные чанки, не ломая структуры ссылок
        text_chunks = safe_split_markdown(final_text, max_size=4000)

        if cover_path:
            from aiogram.types import FSInputFile
            photo = FSInputFile(str(cover_path))
            
            # Если первый кусок влезает в лимит подписи к фото (1024 символа)
            if len(text_chunks[0]) <= 1024:
                await bot.send_photo(chat_id=channel_id, photo=photo, caption=text_chunks[0], parse_mode="Markdown")
                # Остальные куски валятся следом в текстовых сообщениях
                for chunk in text_chunks[1:]:
                    await bot.send_message(chat_id=channel_id, text=chunk, parse_mode="Markdown")
            else:
                # Если статья огромная — шлем обложку с H1 заголовком, а весь текст отправляем следом
                caption_text = f"# {title}" if title else "Новая публикация"
                await bot.send_photo(chat_id=channel_id, photo=photo, caption=caption_text, parse_mode="Markdown")
                for chunk in text_chunks:
                    await bot.send_message(chat_id=channel_id, text=chunk, parse_mode="Markdown")
        else:
            # Обложки нет — просто гоним текстовые чанки по очереди
            for chunk in text_chunks:
                await bot.send_message(chat_id=channel_id, text=chunk, parse_mode="Markdown")
        
        print("Пост успешно отформатирован в Standard Markdown и отправлен в Telegram.")
    except Exception as e:
        print(f"Критическая ошибка отправки в API Telegram: {e}")
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())