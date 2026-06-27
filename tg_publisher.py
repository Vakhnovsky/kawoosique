import os
import sys
import asyncio
import frontmatter
import re
import aiohttp
import mimetypes
from aiogram import Bot
from aiogram.types import InputRichMessage

# Технические константы проекта KAWOOSIQUE
DOMAIN = "https://kawoosique.com"
RHASH = "5dda3eb0d9e2b1"

# Служебный маркер для Instant View
TG_MARKER = "<!--tg-->"

async def upload_to_telegraph(file_path: str) -> str:
    """
    Загружает локальный файл на сервер Telegra.ph и возвращает прямой URL.
    """
    url = "https://telegra.ph/upload"
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "image/jpeg"

    data = aiohttp.FormData()
    try:
        with open(file_path, "rb") as f:
            data.add_field(
                "file",
                f.read(),
                filename=os.path.basename(file_path),
                content_type=mime_type
            )
    except Exception as e:
        print(f"   ❌ [Telegraph] Ошибка чтения файла: {e}")
        return None

    headers = {
        "Origin": "https://telegra.ph",
        "Referer": "https://telegra.ph/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=data, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if isinstance(result, list) and len(result) > 0:
                        img_path = result[0].get("src")
                        full_url = f"https://telegra.ph{img_path}"
                        print(f"   🔥 [Telegraph] Успешно загружено: {full_url}")
                        return full_url
                print(f"   ❌ [Telegraph] Ошибка загрузки. Статус: {resp.status}")
        except Exception as e:
            print(f"   ❌ [Telegraph] Исключение при загрузке: {e}")
    return None

async def upload_to_catbox(file_path: str) -> str:
    """
    Резервный загрузчик на Catbox.moe. 
    Используется, если Telegra.ph блокирует запросы из GitHub Actions (ошибка 400/403).
    """
    url = "https://catbox.moe/user/api.php"
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "image/jpeg"

    data = aiohttp.FormData()
    data.add_field("reqtype", "fileupload")
    try:
        with open(file_path, "rb") as f:
            data.add_field(
                "fileToUpload",
                f.read(),
                filename=os.path.basename(file_path),
                content_type=mime_type
            )
    except Exception as e:
        print(f"   ❌ [Catbox] Ошибка чтения файла: {e}")
        return None

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=data, timeout=30) as resp:
                if resp.status == 200:
                    uploaded_url = await resp.text()
                    uploaded_url = uploaded_url.strip()
                    if uploaded_url.startswith("https://files.catbox.moe"):
                        print(f"   🚀 [Catbox] Успешная резервная загрузка: {uploaded_url}")
                        return uploaded_url
                print(f"   ❌ [Catbox] Сбой загрузки. Статус: {resp.status}")
        except Exception as e:
            print(f"   ❌ [Catbox] Исключение при загрузке: {e}")
    return None

async def upload_image_to_cloud(file_path: str) -> str:
    """
    Универсальный загрузчик изображений с автоматическим переключением на резервный хостинг.
    """
    if not os.path.exists(file_path):
        print(f"⚠️ Файл не найден локально: {file_path}")
        return None

    filename = os.path.basename(file_path)
    print(f"⚙️ Загрузка картинки: {filename}")

    # Попытка 1: Telegra.ph
    print("   👉 Шаг 1: Пробуем загрузить на Telegra.ph...")
    uploaded_url = await upload_to_telegraph(file_path)
    if uploaded_url:
        return uploaded_url

    # Попытка 2: Catbox.moe (Резерв)
    print("   ⚠️ Telegra.ph заблокировал запрос (CF 400/403). Включаем резервный Catbox.moe...")
    uploaded_url = await upload_to_catbox(file_path)
    if uploaded_url:
        return uploaded_url

    print("   ❌ Все облачные загрузчики завершились ошибкой.")
    return None

async def transform_markdown(file_path):
    """
    Парсит Front Matter заметки Obsidian, загружает локальные изображения
    на внешние хостинги с каскадным отказом и форматирует тело под Rich Markdown.
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
    
    local_dir = os.path.dirname(file_path)
    replacements = {}
    
    # 1. Обработка и загрузка обложки (Cover)
    cover_url = ""
    cover_data = post.get('cover', {})
    if cover_data and isinstance(cover_data, dict):
        cover_img = cover_data.get('image', '')
        if cover_img:
            if cover_img.startswith(('http://', 'https://')):
                cover_url = cover_img
            else:
                cover_img_clean = cover_img.lstrip("./").lstrip("/")
                local_cover_path = os.path.join(local_dir, cover_img_clean)
                uploaded_url = await upload_image_to_cloud(local_cover_path)
                if uploaded_url:
                    cover_url = uploaded_url
                else:
                    # Резервный URL на твоем сайте на случай полного сбоя сети
                    cover_url = f"{DOMAIN}/{dirname}/{cover_img_clean}"
                    
    # 2. Поиск и асинхронная загрузка локальных картинок из тела поста
    img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
    matches = img_pattern.findall(content)
    
    for alt_text, img_path in matches:
        if img_path.startswith(('http://', 'https://')):
            continue
        if img_path not in replacements:
            img_path_clean = img_path.lstrip("./").lstrip("/")
            local_img_path = os.path.join(local_dir, img_path_clean)
            uploaded_url = await upload_image_to_cloud(local_img_path)
            if uploaded_url:
                replacements[img_path] = uploaded_url
            else:
                # Резервный URL на твоем сайте
                replacements[img_path] = f"{DOMAIN}/{dirname}/{img_path_clean}"
                
    # Заменяем локальные пути в Markdown тексте на облачные ссылки
    def replace_image_links(match):
        alt_text = match.group(1)
        img_path = match.group(2)
        if img_path in replacements:
            return f"![{alt_text}]({replacements[img_path]})"
        return match.group(0)
        
    content = img_pattern.sub(replace_image_links, content)
    
    # Формируем итоговое сообщение для Telegram
    header = f"# {title}\n\n"
    
    post_url = f"{DOMAIN}/{dirname}/"
    iv_url = f"https://t.me/iv?url={post_url}&rhash={RHASH}"
    
    # Встраиваем обложку в начало как невидимую ссылку
    preview_link = ""
    if cover_url:
        preview_link = f"[\u00AD]({cover_url})"
    else:
        preview_link = f"[\u00AD]({iv_url})"
        
    rich_text = f"{preview_link}{header}{content}"
    return rich_text

async def main(file_path):
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
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python tg_publisher.py <путь_к_md_файлу>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))