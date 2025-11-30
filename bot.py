import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import cv2
import numpy as np
from moviepy.editor import VideoFileClip
import tempfile

# ===== КОНФИГУРАЦИЯ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    exit(1)


class VideoBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        self.application.add_error_handler(self.error_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user = update.message.from_user
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "🎥 Я бот для создания кружочков видеосообщений!\n\n"
            "Просто отправь мне видео, и я преобразую его в кружочек!"
        )
        logger.info(f"Пользователь {user.first_name} запустил бота")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        await update.message.reply_text(
            "📋 **Помощь:**\n\n"
            "• Отправь видео файл → получи кружочек\n"
            "• Видео до 20 секунд\n"
            "• Размер до 50 МБ\n\n"
            "Команды:\n"
            "/start - начать\n"
            "/help - помощь\n"
            "/status - статус бота"
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        await update.message.reply_text("✅ Бот работает исправно! Отправь мне видео 🎬")

    def create_circle_video(self, input_path, output_path):
        """Создание круглого видео"""
        try:
            with VideoFileClip(input_path) as clip:
                # Ограничение длительности
                if clip.duration > 20:
                    clip = clip.subclip(0, 20)

                # Создание квадрата
                width, height = clip.size
                size = min(width, height)
                x_center, y_center = width // 2, height // 2

                cropped_clip = clip.crop(
                    x1=x_center - size // 2,
                    y1=y_center - size // 2,
                    width=size,
                    height=size
                )

                # Круглая маска
                def apply_circle_mask(frame):
                    mask = np.zeros((size, size, 3), dtype=np.uint8)
                    cv2.circle(mask, (size // 2, size // 2), size // 2, (255, 255, 255), -1)
                    return cv2.bitwise_and(frame, mask)

                circle_clip = cropped_clip.fl(apply_circle_mask)
                circle_clip = circle_clip.set_fps(30)

                # Сохранение
                circle_clip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    verbose=False,
                    logger=None
                )

            return True

        except Exception as e:
            logger.error(f"Ошибка обработки видео: {e}")
            return False

    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка видео"""
        user = update.message.from_user
        logger.info(f"📹 Видео от {user.first_name}")

        processing_msg = await update.message.reply_text("🔄 Обрабатываю видео...")

        try:
            # Скачивание
            video_file = await update.message.video.get_file()

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_temp:
                input_path = input_temp.name

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_temp:
                output_path = output_temp.name

            await video_file.download_to_drive(input_path)

            # Обработка
            await processing_msg.edit_text("🎬 Создаю кружочек...")
            success = self.create_circle_video(input_path, output_path)

            if success:
                await processing_msg.edit_text("✅ Отправляю...")
                with open(output_path, 'rb') as result_file:
                    await update.message.reply_video_note(video_note=result_file, length=320)
                await processing_msg.delete()
            else:
                await processing_msg.edit_text("❌ Ошибка обработки")

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await processing_msg.edit_text("❌ Ошибка, попробуйте позже")

        finally:
            # Очистка
            for path in [input_path, output_path]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except:
                    pass

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Ошибка бота: {context.error}")

    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск бота на GitHub...")
        self.application.run_polling()


if __name__ == "__main__":
    bot = VideoBot()
    bot.run()