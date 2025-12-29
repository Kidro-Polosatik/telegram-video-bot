import os
import logging
import asyncio
import signal
import sys
import time
import tempfile
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from moviepy.editor import VideoFileClip

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

# Флаг для graceful shutdown
shutdown_flag = False

class VideoBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        self.should_stop = False
    
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
            "3. Получишь кружочек видеосообщение!\n\n"
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
        """Создание квадратного видео для видеосообщения"""
        try:
            logger.info(f"🎬 Начинаю обработку: {input_path} -> {output_path}")
            
            with VideoFileClip(input_path) as clip:
                logger.info(f"📹 Видео загружено: {clip.size[0]}x{clip.size[1]}, {clip.duration}сек")
                
                # Ограничение длительности
                if clip.duration > 20:
                    clip = clip.subclip(0, 20)
                
                # Создание квадрата
                width, height = clip.size
                size = min(width, height)
                x_center, y_center = width // 2, height // 2
                
                cropped_clip = clip.crop(
                    x1=x_center - size//2,
                    y1=y_center - size//2,
                    width=size,
                    height=size
                )
                
                # Ресайзим до оптимального размера
                target_size = 320
                resized_clip = cropped_clip.resize(newsize=(target_size, target_size))
                
                # Сохраняем
                resized_clip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    verbose=False,
                    logger=None
                )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки видео: {e}")
            return False
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка видео"""
        user = update.message.from_user
        logger.info(f"📹 Получено видео от {user.first_name}")
        
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
                await processing_msg.edit_text("✅ Отправляю видеосообщение...")
                
                with open(output_path, 'rb') as result_file:
                    await update.message.reply_video_note(
                        video_note=result_file,
                        length=320,
                        duration=min(update.message.video.duration, 20)
                    )
                
                await processing_msg.delete()
                logger.info("✅ Видеосообщение отправлено")
                
            else:
                await processing_msg.edit_text("❌ Не удалось обработать видео")
        
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
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
        
        if "Conflict" in str(error):
            logger.info("⚠️ Конфликт getUpdates - другой инстанс бота активен")
            return
        
        if update and update.message:
            try:
                await update.message.reply_text("❌ Ошибка, попробуйте позже")
            except:
                pass

    def run(self):
        """Запуск бота с таймером"""
        logger.info("🚀 Запуск бота...")
        
        try:
            # Сбрасываем webhook
            webhook_url = f"https://api.telegram.org/bot{self.application.bot.token}/deleteWebhook"
            response = requests.get(webhook_url)
            logger.info(f"🔧 Webhook сброшен: {response.status_code}")
            
            # Запускаем polling в отдельном потоке
            import threading
            
            def polling_thread():
                self.application.run_polling(
                    poll_interval=3,
                    timeout=20,
                    drop_pending_updates=True
                )
            
            thread = threading.Thread(target=polling_thread)
            thread.daemon = True
            thread.start()
            
            # Ждем 5 часов 45 минут, затем останавливаемся
            logger.info("⏰ Бот запущен. Автоматический перезапуск через 5 часов 45 минут...")
            time.sleep(5 * 60 * 60 + 45 * 60)  # 5 часов 45 минут
            
            logger.info("🔄 Время перезапуска! Останавливаю бота...")
            self.application.stop()
            thread.join(timeout=10)
            
            logger.info("✅ Бот остановлен. GitHub Actions перезапустит workflow.")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            sys.exit(1)

def signal_handler(signum, frame):
    """Обработчик сигналов"""
    global shutdown_flag
    logger.info(f"📞 Получен сигнал {signum}")
    shutdown_flag = True

def main():
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
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