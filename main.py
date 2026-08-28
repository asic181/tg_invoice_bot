import io
import os
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения ДО импорта других сервисов
load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bitrix_service import create_invoice_in_bitrix

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_CHATS = [
    int(chat_id.strip()) 
    for chat_id in os.getenv("ALLOWED_CHAT_IDS", "").split(",") 
    if chat_id.strip()
]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(F.chat.id.in_(ALLOWED_CHATS), F.document | F.photo)
async def handle_invoice_file(message: Message):
    # Определение документа или фото
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "invoice.pdf"
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f"invoice_{photo.file_unique_id}.jpg"
    else:
        return

    user = message.from_user
    user_name = user.full_name or user.first_name
    tg_username = user.username or "без_username"
    comment = message.caption or "Без комментария"

    status_msg = await message.reply("⏳ Загружаю счет и создаю запись в Битрикс24...")

    try:
        # Скачиваем файл в оперативную память
        file_info = await bot.get_file(file_id)
        file_bytes_io = io.BytesIO()
        await bot.download_file(file_info.file_path, destination=file_bytes_io)
        file_bytes = file_bytes_io.getvalue()

        # Отправляем в Битрикс24
        crm_result = await create_invoice_in_bitrix(
            file_bytes=file_bytes,
            file_name=file_name,
            user_name=user_name,
            comment=comment,
            tg_username=tg_username
        )

        reply_text = (
            f"✅ <b>Счет успешно зарегистрирован в Битрикс24!</b>\n\n"
            f"• <b>Номер счета:</b> <code>#{crm_result['id']}</code>\n"
            f"• <b>Отправитель:</b> {user_name} (@{tg_username})\n"
            f"• <b>Комментарий:</b> {comment}\n"
            f"• <b>Файл:</b> {file_name}\n\n"
            f"🔗 <a href=\"{crm_result['url']}\">Перейти к счету в Битрикс24</a>"
        )
        await status_msg.edit_text(reply_text, disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Ошибка при обработке счета: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ <b>Ошибка при сохранении счета:</b>\n<code>{str(e)}</code>"
        )


async def main():
    logging.info("Бот запущен и ожидает файлы в группе...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())