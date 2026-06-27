import os
import sys
import asyncio
import re
import yaml
from pathlib import Path
from aiogram import Bot
from aiogram.types import InputRichMessage

async def main():
    # Задержка для обновления инфраструктуры GitHub
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

    # Извлекаем Front Matter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        fm_raw = fm_match.group(1)
        body = fm_match.group(2)
        try:
            metadata = yaml.safe_load(fm_raw) or {}
        except Exception as e:
            metadata = {}
    else:
        metadata = {}
        body = content

    # Проверка активности публикации
    if not metadata.get('tg_publish', True):
        sys.exit(0)

    # Пути для Raw-ссылок
    rel_dir = path.parent.resolve().relative_to(Path(os.getcwd()).resolve())
    post_dir_path = str(rel_dir).replace("\\", "/")
    base_url = f"https://raw.githubusercontent.com/{repo}/main/{post_dir_path}"

    # Парсинг картинок: оставляем синтаксис Markdown, подставляя правильный URL
    def replace_images(match):
        alt = match.group(1) or ""
        img = match.group(2)
        if img.startswith(('http://', 'https://')):
            return match.group(0)
        return f"![{alt}]({base_url}/{os.path.basename(img)})"

    # Обработка ![alt](image) и ![[image]]
    body = re.sub(r'!\[(.*?)\]\((.*?)\)', replace_images, body)
    body = re.sub(r'!\[\[(.*?)\]\]', lambda m: f"![Изображение]({base_url}/{m.group(1).split('|')[0].strip()})", body)

    # Сборка текста: заголовки #/##/### теперь НЕ трогаем
    title = metadata.get('title', '')
    header = f"# {title}\n\n" if title else ""
    
    tags_list = metadata.get('tags', [])
    formatted_tags = ""
    if tags_list and isinstance(tags_list, list):
        tags = [f"#{re.sub(r'[^\w\d_]', '', str(t).replace(' ', '_'))}" for t in tags_list]
        formatted_tags = "\n\n" + " ".join(tags)

    final_text = f"{header}{body.strip()}{formatted_tags}"

    bot = Bot(token=bot_token)
    
    try:
        # Прямая отправка Rich Message
        await bot.send_message(
            chat_id=channel_id,
            text=final_text,
            message_effect_id=None # можно добавить, если нужно
        )
        # Примечание: В API 10.1 для Rich Message мы передаем текст в поле markdown или используем message_entities
        print("Пост успешно опубликован через Rich-Format.")
    except Exception as e:
        print(f"Ошибка API 10.1: {e}")
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())