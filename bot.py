import os
import logging
import signal
import sys
import time
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
    sys.exit(1)

logger.info(f"✅ BOT_TOKEN загружен (первые символы: {BOT_TOKEN[:10]}...)")


class VideoBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        self.restart_count = 0
        self.max_restarts = 3

    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("formats", self.supported_formats))
        self.application.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        self.application.add_error_handler(self.error_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "🎥 Я бот для создания кружочков видеосообщений!\n\n"
            "Просто отправь мне видео, и я преобразую его в кружочек!"
        )
        logger.info(f"Пользователь {user.first_name} запустил бота")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 **Помощь:**\n\n"
            "1. Отправь видео файл\n"
            "2. Я обработаю его\n"
            "3. Получишь кружочек!\n\n"
            "Поддерживаемые форматы: MP4, MOV, AVI, MKV, WEBM\n"
            "Ограничения: до 50 МБ, до 60 секунд"
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Бот работает! Отправь видео 🎬")

    async def supported_formats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📹 **Форматы:** MP4, MOV, AVI, MKV, WEBM\n"
            "🎯 **Идеально:** MP4, 5-15 сек, 10-20 МБ"
        )

    def create_circle_video(self, input_path, output_path):
        try:
            with VideoFileClip(input_path) as clip:
                if clip.duration > 20:
                    clip = clip.subclip(0, 20)

                width, height = clip.size
                size = min(width, height)
                x_center, y_center = width // 2, height // 2

                cropped_clip = clip.crop(
                    x1=x_center - size // 2,
                    y1=y_center - size // 2,
                    width=size,
                    height=size
                )

                def apply_circle_mask(frame):
                    mask = np.zeros((size, size, 3), dtype=np.uint8)
                    cv2.circle(mask, (size // 2, size // 2), size // 2, (255, 255, 255), -1)
                    return cv2.bitwise_and(frame, mask)

                circle_clip = cropped_clip.fl(apply_circle_mask)
                circle_clip = circle_clip.set_fps(30)

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
        user = update.message.from_user
        logger.info(f"📹 Видео от {user.first_name}")

        input_path = None
        output_path = None

        try:
            if update.message.video.file_size > 50 * 1024 * 1024:
                await update.message.reply_text("❌ Файл слишком большой! Максимум 50 МБ")
                return

            processing_msg = await update.message.reply_text("🔄 Обрабатываю видео...")

            video_file = await update.message.video.get_file()

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
                input_path = input_file.name

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                output_path = output_file.name

            await video_file.download_to_drive(input_path)

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
            await update.message.reply_text("❌ Ошибка, попробуйте позже")

        finally:
            for path in [input_path, output_path]:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except:
                    pass

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        error = context.error
        logger.error(f"❌ Ошибка бота: {error}")

        # Игнорируем ошибки конфликта - они нормальны при перезапусках
        if "Conflict" in str(error):
            logger.info("⚠️ Конфликт getUpdates - другой инстанс бота активен")
            return

        if update and update.message:
            try:
                await update.message.reply_text("❌ Ошибка, попробуйте позже")
            except:
                pass

    def run(self):
        """Запуск бота с обработкой ошибок"""
        logger.info("🚀 Запуск бота...")

        try:
            self.application.run_polling(
                poll_interval=3,
                timeout=20,
                drop_pending_updates=True  # ⭐ Важно: игнорируем старые сообщения
            )
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            if self.restart_count < self.max_restarts:
                self.restart_count += 1
                logger.info(f"🔄 Перезапуск {self.restart_count}/{self.max_restarts}...")
                time.sleep(5)
                self.run()
            else:
                logger.error("❌ Достигнут лимит перезапусков")
                sys.exit(1)


def main():
    logger.info("🚀 Telegram Video Circle Bot запускается...")

    try:
        bot = VideoBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Завершение работы по запросу пользователя")
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()