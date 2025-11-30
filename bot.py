import os
import logging
import asyncio
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
        """Команда /start"""
        user = update.message.from_user
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "🎥 Я бот для создания кружочков видеосообщений!\n\n"
            "Просто отправь мне видео, и я преобразую его в кружочек!\n\n"
            "📋 **Поддерживаемые форматы:**\n"
            "• MP4, MOV, AVI, MKV\n"
            "• WEBM, WMV, MPEG, 3GP\n\n"
            "⚠️ **Ограничения:**\n"
            "• До 50 МБ\n"
            "• До 60 секунд (обрежется до 20)\n\n"
            "🎯 **Идеальное видео:**\n"
            "• MP4 формат\n"
            "• 5-15 секунд\n"
            "• 10-20 МБ размер"
        )
        logger.info(f"Пользователь {user.first_name} запустил бота")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        await update.message.reply_text(
            "📋 **Помощь по использованию бота:**\n\n"
            "**Как использовать:**\n"
            "1. Отправь видео файл\n"
            "2. Я обработаю его\n"
            "3. Получишь кружочек!\n\n"
            "**Команды:**\n"
            "/start - начать работу\n"
            "/help - эта справка\n"
            "/status - статус бота\n"
            "/formats - поддерживаемые форматы\n\n"
            "**Если возникли проблемы:**\n"
            "• Попробуй конвертировать видео в MP4\n"
            "• Уменьши длительность до 15 секунд\n"
            "• Убедись, что размер до 50 МБ"
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        await update.message.reply_text(
            "✅ Бот работает исправно!\n"
            "🟢 Готов к обработке видео\n"
            "📹 Отправь мне видео и получи кружочек! 🎬"
        )

    async def supported_formats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /formats"""
        await update.message.reply_text(
            "📹 **Поддерживаемые форматы видео:**\n\n"
            "✅ **Отлично работают:**\n"
            "• MP4 (.mp4) - рекомендуется\n"
            "• MOV (.mov)\n"
            "• AVI (.avi)\n"
            "• MKV (.mkv)\n\n"
            "✅ **Обычно работают:**\n"
            "• WEBM (.webm)\n"
            "• WMV (.wmv)\n"
            "• MPEG (.mpeg, .mpg)\n"
            "• 3GP (.3gp)\n\n"
            "⚠️ **С ограничениями:**\n"
            "• GIF - без звука\n"
            "• M4V - может требовать конвертации\n\n"
            "🎯 **Идеальные параметры:**\n"
            "• Формат: MP4 (H.264 + AAC)\n"
            "• Длительность: 5-15 секунд\n"
            "• Размер: 10-20 МБ\n"
            "• Разрешение: 720x720"
        )

    def create_circle_video(self, input_path, output_path):
        """Создание круглого видео"""
        try:
            logger.info(f"🎬 Начинаю обработку: {input_path} -> {output_path}")

            # Проверяем что файл существует и не пустой
            if not os.path.exists(input_path):
                logger.error("❌ Входной файл не существует")
                return False

            file_size = os.path.getsize(input_path)
            if file_size == 0:
                logger.error("❌ Входной файл пустой")
                return False

            logger.info(f"📁 Размер входного файла: {file_size} байт")

            with VideoFileClip(input_path) as clip:
                logger.info(f"📹 Видео загружено: {clip.size[0]}x{clip.size[1]}, {clip.duration}сек")

                # Ограничение длительности
                original_duration = clip.duration
                if original_duration > 20:
                    clip = clip.subclip(0, 20)
                    logger.info(f"⏰ Видео обрезано с {original_duration:.1f}с до 20с")

                # Создание квадрата
                width, height = clip.size
                size = min(width, height)
                x_center, y_center = width // 2, height // 2

                logger.info(f"🔲 Исходное разрешение: {width}x{height}, обрезается до: {size}x{size}")

                cropped_clip = clip.crop(
                    x1=x_center - size // 2,
                    y1=y_center - size // 2,
                    width=size,
                    height=size
                )

                # Круглая маска
                def apply_circle_mask(get_frame, t):
                    frame = get_frame(t)
                    mask = np.zeros((size, size, 3), dtype=np.uint8)
                    cv2.circle(mask, (size//2, size//2), size//2, (255, 255, 255), -1)
                    return cv2.bitwise_and(frame, mask)

                logger.info("🎭 Применяю круглую маску...")
                circle_clip = cropped_clip.fl(apply_circle_mask)
                circle_clip = circle_clip.set_fps(30)

                # Сохранение
                logger.info("💾 Сохраняю результат...")
                circle_clip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    verbose=False,
                    logger=None,
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True
                )

            logger.info("✅ Видео успешно обработано")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка обработки видео: {e}", exc_info=True)
            return False

    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка видео с проверкой форматов"""
        user = update.message.from_user
        logger.info(f"📹 Получено видео от {user.first_name}")

        # ⭐ ДОБАВЛЕНА ОТЛАДОЧНАЯ ИНФОРМАЦИЯ
        logger.info(f"📊 Информация о видео:")
        logger.info(f"   - Размер: {update.message.video.file_size} байт")
        logger.info(f"   - Длительность: {update.message.video.duration} сек")
        logger.info(f"   - MIME тип: {update.message.video.mime_type}")

        input_path = None
        output_path = None

        try:
            # Проверяем размер файла
            if update.message.video.file_size > 50 * 1024 * 1024:  # 50 МБ
                await update.message.reply_text(
                    "❌ Файл слишком большой! Максимум 50 МБ\n"
                    "📏 Попробуйте:\n"
                    "• Сжать видео\n"
                    "• Выбрать короче\n"
                    "• Уменьшить качество"
                )
                return

            # Проверяем длительность
            video_duration = update.message.video.duration
            if video_duration > 60:  # 60 секунд
                await update.message.reply_text(
                    f"⚠️ Видео длинное: {video_duration} секунд\n"
                    "⏰ Бот обрежет до 20 секунд"
                )

            processing_msg = await update.message.reply_text("🔄 Проверяю видео...")

            # Скачиваем видео
            video_file = await update.message.video.get_file()
            file_extension = video_file.file_path.split('.')[-1].lower() if video_file.file_path else 'mp4'

            logger.info(f"📥 Скачиваю видео: {file_extension}")

            await processing_msg.edit_text(
                f"📹 **Информация о видео:**\n"
                f"• Формат: {file_extension.upper()}\n"
                f"• Длительность: {video_duration} сек\n"
                f"• Размер: {update.message.video.file_size // (1024 * 1024)} МБ\n\n"
                f"🔄 Начинаю обработку..."
            )

            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as input_file:
                input_path = input_file.name

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                output_path = output_file.name

            await video_file.download_to_drive(input_path)
            logger.info(f"✅ Видео скачано: {input_path}")

            # Проверяем что файл скачался
            file_size = os.path.getsize(input_path)
            logger.info(f"📦 Размер скачанного файла: {file_size} байт")

            if file_size == 0:
                await processing_msg.edit_text("❌ Ошибка: файл пустой")
                return

            # Обработка
            await processing_msg.edit_text("🎬 Создаю кружочек...")
            logger.info("🔄 Начинаю обработку видео...")

            success = self.create_circle_video(input_path, output_path)

            if success:
                await processing_msg.edit_text("✅ Отправляю результат...")

                # Получаем размер обработанного файла
                output_size = os.path.getsize(output_path) // (1024 * 1024)
                logger.info(f"📦 Размер обработанного видео: {output_size} МБ")

                with open(output_path, 'rb') as result_file:
                    await update.message.reply_video_note(
                        video_note=result_file,
                        length=320,
                        duration=min(video_duration, 20)
                    )

                await processing_msg.delete()
                logger.info("✅ Видеосообщение отправлено")

            else:
                await processing_msg.edit_text(
                    "❌ Не удалось обработать это видео\n\n"
                    "💡 **Попробуйте:**\n"
                    "• Конвертировать в MP4\n"
                    "• Уменьшить размер\n"
                    "• Сделать короче\n"
                    "• Убрать сложные эффекты\n\n"
                    "📋 Или используйте команду /formats для справки"
                )
                logger.error("❌ Ошибка обработки видео")

        except Exception as e:
            logger.error(f"❌ Ошибка в handle_video: {e}", exc_info=True)
            if update.message:
                await update.message.reply_text(
                    f"❌ Ошибка обработки: {str(e)}\n\n"
                    "📋 Попробуйте другое видео или используйте /help"
                )

        finally:
            # Очистка временных файлов
            for path in [input_path, output_path]:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                        logger.info(f"✅ Временный файл удален: {path}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить временный файл: {e}")

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