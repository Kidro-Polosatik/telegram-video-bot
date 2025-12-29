import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from moviepy.editor import VideoFileClip

# Конфигурация
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    exit(1)

logger.info("✅ Бот запускается...")

class VideoBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Привет! Я бот для создания кружочков видеосообщений!\n\n"
            "📹 Просто отправь мне видео, и я сделаю из него кружочек!\n\n"
            "⚠️ Ограничения:\n• До 50 МБ\n• До 20 секунд"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 Как использовать:\n1. Отправь видео\n2. Получи кружочек!\n\n"
            "Поддерживаемые форматы: MP4, MOV, AVI"
        )
    
    def create_square_video(self, input_path, output_path):
        """Создание квадратного видео"""
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
                    x1=x_center - size//2,
                    y1=y_center - size//2,
                    width=size,
                    height=size
                )
                
                # Ресайз до 640x640
                resized_clip = cropped_clip.resize(newsize=(640, 640))
                
                # Сохранение
                resized_clip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    verbose=False,
                    logger=None
                )
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка обработки: {e}")
            return False
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка видео"""
        try:
            if update.message.video.file_size > 50 * 1024 * 1024:
                await update.message.reply_text("❌ Файл слишком большой! Максимум 50 МБ")
                return
            
            processing_msg = await update.message.reply_text("🔄 Обрабатываю видео...")
            
            # Скачиваем видео
            video_file = await update.message.video.get_file()
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
                input_path = input_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                output_path = output_file.name
            
            await video_file.download_to_drive(input_path)
            
            await processing_msg.edit_text("🎬 Создаю кружочек...")
            
            if self.create_square_video(input_path, output_path):
                await processing_msg.edit_text("✅ Отправляю...")
                
                with open(output_path, 'rb') as result_file:
                    await update.message.reply_video_note(
                        video_note=result_file,
                        length=640,
                        duration=min(update.message.video.duration, 20)
                    )
                
                await processing_msg.delete()
            else:
                await processing_msg.edit_text("❌ Ошибка обработки")
        
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            await update.message.reply_text("❌ Ошибка, попробуйте позже")
        
        finally:
            # Очистка файлов
            for path in [input_path, output_path]:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except:
                    pass
    
    def run(self):
        """Запуск бота"""
        self.application.run_polling()

def main():
    bot = VideoBot()
    bot.run()

if __name__ == "__main__":
    main()