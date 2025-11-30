import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import cv2
import numpy as np
from moviepy.editor import VideoFileClip

# ===== КОНФИГУРАЦИЯ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден! Установите переменную окружения BOT_TOKEN")
    exit(1)


# ===== ОСНОВНЫЕ ФУНКЦИИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
🎥 **Video Circle Bot**

Привет! Я преобразую обычные видео в кружочки видеосообщений Telegram.

**Как использовать:**
1. Просто отправь мне видео файл
2. Я обработаю его и создам кружочек
3. Получишь готовое видеосообщение!

**⚠️ Ограничения:**
• Длительность: до 20 секунд
• Размер: до 50 МБ
• Форматы: MP4, MOV, AVI и другие

**Отправь мне видео и попробуй!** 🎬
    """
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📋 **Помощь по использованию бота:**

**Доступные команды:**
/start - начать работу
/help - показать эту справку

**Просто отправь видео файл** (не видеосообщение), и я преобразую его в кружочек.

**Поддерживаемые форматы:** MP4, MOV, AVI, MKV, WEBM

**Если возникли проблемы:**
• Убедись, что видео не слишком длинное
• Попробуй перезапустить бот командой /start
    """
    await update.message.reply_text(help_text)


def create_circle_video(input_path, output_path):
    """Создает видео в круглом формате"""
    try:
        # Загружаем видео
        clip = VideoFileClip(input_path)

        # Ограничиваем длительность до 20 секунд
        if clip.duration > 20:
            clip = clip.subclip(0, 20)
            logger.info(f"Видео обрезано до 20 секунд")

        # Получаем размеры видео
        width, height = clip.size
        logger.info(f"Исходный размер видео: {width}x{height}")

        # Создаем квадратное видео (1:1)
        size = min(width, height)
        x_center = width // 2
        y_center = height // 2

        # Обрезаем видео до квадрата
        cropped_clip = clip.crop(
            x1=x_center - size // 2,
            y1=y_center - size // 2,
            width=size,
            height=size
        )

        # Создаем маску для круглой формы
        def make_circle_frame(get_frame, t):
            frame = get_frame(t)
            mask = np.zeros((size, size, 3), dtype=np.uint8)
            cv2.circle(mask, (size // 2, size // 2), size // 2, (255, 255, 255), -1)
            result = cv2.bitwise_and(frame, mask)
            return result

        # Применяем маску
        circle_clip = cropped_clip.fl(make_circle_frame)

        # Устанавливаем параметры для видеосообщения
        circle_clip = circle_clip.set_fps(30)

        # Сохраняем результат
        circle_clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            verbose=False,
            logger=None
        )

        # Закрываем клипы
        clip.close()
        cropped_clip.close()
        circle_clip.close()

        logger.info("✅ Видео успешно обработано")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при создании круглого видео: {e}")
        return False


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик видеофайлов"""
    user = update.message.from_user
    logger.info(f"📹 Получено видео от {user.first_name} (ID: {user.id})")

    try:
        # Отправляем сообщение о начале обработки
        processing_msg = await update.message.reply_text("🔄 Скачиваю и обрабатываю видео...")

        # Скачиваем видео
        video_file = await update.message.video.get_file()

        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
            input_path = input_file.name

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
            output_path = output_file.name

        try:
            # Скачиваем видео
            await video_file.download_to_drive(input_path)
            logger.info("✅ Видео скачано")

            # Создаем круглое видео
            await processing_msg.edit_text("🎬 Создаю кружочек...")

            success = create_circle_video(input_path, output_path)

            if success and os.path.exists(output_path):
                # Отправляем результат
                await processing_msg.edit_text("✅ Отправляю результат...")

                with open(output_path, 'rb') as video_file:
                    await update.message.reply_video_note(
                        video_note=video_file,
                        duration=min(update.message.video.duration, 20),
                        length=320  # Размер видеосообщения
                    )

                await processing_msg.delete()
                logger.info("✅ Видеосообщение отправлено пользователю")

            else:
                await processing_msg.edit_text("❌ Не удалось обработать видео. Попробуйте другое видео.")
                logger.error("❌ Ошибка обработки видео")

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке видео: {e}")
            await processing_msg.edit_text("❌ Произошла ошибка при обработке видео. Попробуйте позже.")

        finally:
            # Удаляем временные файлы
            for file_path in [input_path, output_path]:
                if os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                        logger.info("✅ Временные файлы удалены")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить временный файл: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка в handle_video: {e}")
        await update.message.reply_text("❌ Произошла непредвиденная ошибка. Попробуйте позже.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Ошибка: {context.error}")

    if update and update.message:
        await update.message.reply_text("❌ Произошла непредвиденная ошибка. Попробуйте позже.")


def main():
    """Основная функция"""
    logger.info("🚀 Запуск Telegram Video Circle Bot...")

    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("✅ Бот запущен и готов к работе!")
    application.run_polling()


if __name__ == "__main__":
    main()