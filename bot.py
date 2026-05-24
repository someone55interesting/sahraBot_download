import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= НАСТРОЙКИ =================
# Токен бота берётся из переменной окружения BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Не задан BOT_TOKEN! Проверь переменные окружения.")

# URL твоего Cobalt API (обязательно с /api/json на конце!)
COBALT_API_URL = os.getenv("COBALT_API_URL", "https://my-cobalt-api-vp1b.onrender.com/")

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= ОСНОВНАЯ ЛОГИКА =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветствие при команде /start"""
    await update.message.reply_text(
        "👋 Привет! Отправь мне ссылку на видео из TikTok, Instagram или YouTube, "
        "и я пришлю его без водяного знака.\n\n"
        "Поддерживаются короткие ссылки и полные URL."
    )

def extract_url(text: str) -> str | None:
    """Грубо проверяем, есть ли в тексте URL (начинается с http/https)"""
    for word in text.split():
        if word.startswith("http://") or word.startswith("https://"):
            return word
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатываем любое текстовое сообщение, ищем ссылку и отправляем видео"""
    user_text = update.message.text
    url = extract_url(user_text)
    if not url:
        await update.message.reply_text("❌ Не нашёл ссылку в сообщении. Отправь, пожалуйста, полный URL.")
        return

    # Отправляем статус "обрабатывается"
    processing_msg = await update.message.reply_text("⏳ Обрабатываю ссылку...")

    # Запрос к твоему Cobalt API
    try:
        response = requests.post(
            COBALT_API_URL,
            json={"url": url},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()  # вызовет исключение при HTTP ошибках
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к Cobalt: {e}")
        await processing_msg.edit_text("⚠️ Не удалось связаться с сервисом скачивания. Попробуй позже.")
        return
    except ValueError as e:
        logger.error(f"Ошибка разбора JSON от Cobalt: {e}")
        await processing_msg.edit_text("⚠️ Сервис вернул некорректный ответ.")
        return

    # Проверяем статус ответа Cobalt
    if data.get("status") == "error":
        error_text = data.get("error", {}).get("message", "Неизвестная ошибка")
        await processing_msg.edit_text(f"❌ Не удалось скачать: {error_text}")
        return

    # Если всё ок, получаем прямую ссылку на файл
    video_url = data.get("url")
    if not video_url:
        # Возможен формат picker (несколько файлов, как в Instagram-карусели)
        picker = data.get("picker")
        if picker and isinstance(picker, list) and len(picker) > 0:
            video_url = picker[0].get("url")
        if not video_url:
            await processing_msg.edit_text("❌ Не удалось получить ссылку на видео. Ответ сервера:\n" + str(data))
            return

    # Удаляем сообщение "обрабатывается" и отправляем видео
    await processing_msg.delete()
    try:
        await update.message.reply_video(
            video=video_url,
            caption=f"🎥 Вот твоё видео!\nИсточник: {url}",
            supports_streaming=True
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке видео: {e}")
        await update.message.reply_text(
            "⚠️ Не получилось отправить видео напрямую. Возможно, файл слишком большой (>50 МБ). "
            "Попробуй другую ссылку или скачай сам:\n"
            f"{video_url}"
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирование ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ================= ЗАПУСК БОТА =================
def main() -> None:
    """Запуск бота"""
    app = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # Запускаем поллинг
    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()