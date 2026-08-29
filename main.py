import io
import os
import html
import logging
import asyncio
from dotenv import load_dotenv

load_dotenv()

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, LinkPreviewOptions
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


# ==========================================
# 1. ОБРАБОТКА ВХОДЯЩИХ СЧЕТОВ ИЗ TELEGRAM
# ==========================================
@dp.message(F.chat.id.in_(ALLOWED_CHATS), F.document | F.photo)
async def handle_invoice_file(message: Message):
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
    user_name = user.full_name or user.first_name or "Сотрудник"
    tg_username = user.username or "без_username"
    raw_comment = message.caption or "Без комментария"

    status_msg = await message.reply("⏳ Загружаю счет и создаю запись в Битрикс24...")

    try:
        file_info = await bot.get_file(file_id)
        file_bytes_io = io.BytesIO()
        await bot.download_file(file_info.file_path, destination=file_bytes_io)
        file_bytes = file_bytes_io.getvalue()

        # Создаем счет в Битрикс24
        crm_result = await create_invoice_in_bitrix(
            file_bytes=file_bytes,
            file_name=file_name,
            user_name=user_name,
            comment=raw_comment,
            tg_username=tg_username,
            chat_id=message.chat.id,
            message_id=message.message_id
        )

        safe_user_name = html.escape(user_name)
        safe_tg_username = html.escape(tg_username)
        safe_comment = html.escape(raw_comment)
        safe_file_name = html.escape(file_name)
        
        reply_text = (
            f"✅ <b>Счет успешно зарегистрирован в Битрикс24!</b>\n\n"
            f"• <b>Номер счета:</b> <code>#{crm_result['id']}</code>\n"
            f"• <b>Отправитель:</b> {safe_user_name} (@{safe_tg_username})\n"
            f"• <b>Комментарий:</b> {safe_comment}\n"
            f"• <b>Файл:</b> {safe_file_name}\n\n"
            f"🔗 <a href=\"{crm_result['url']}\">Перейти к счету в Битрикс24</a>"
        )
        
        await status_msg.edit_text(
            reply_text, 
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    except Exception as e:
        logging.error(f"Ошибка при обработке счета: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ <b>Ошибка при сохранении счета:</b>\n<code>{html.escape(str(e))}</code>"
        )


# =======================================================
# 2. ВЕБХУК ДЛЯ УВЕДОМЛЕНИЙ ОБ ОПЛАТЕ ИЗ БИТРИКС24
# =======================================================
def clean_val(val: str) -> str:
    """Удаляет фигурные скобки, кавычки и пробелы от макросов Битрикс24."""
    if not val:
        return ""
    return str(val).strip("{}'\" \t\r\n")


async def handle_paid_webhook(request: web.Request):
    """Принимает запрос от робота Битрикс24 и отправляет реплай в группу."""
    try:
        params = request.query
        if not params and request.method == "POST":
            params = await request.post()

        # Извлекаем и очищаем параметры
        raw_chat_id = clean_val(params.get("chat_id", ""))
        raw_reply_to = clean_val(params.get("reply_to_message_id", ""))
        title = clean_val(params.get("title", "Счет"))
        amount = clean_val(params.get("amount", ""))

        logging.info(f"Вебхук оплаты: chat_id={raw_chat_id}, reply_to={raw_reply_to}, title={title}, amount={amount}")

        # Валидация chat_id
        if not raw_chat_id or not (raw_chat_id.lstrip("-").isdigit()):
            logging.warning(f"Пропущен невалидный chat_id: '{raw_chat_id}'")
            return web.Response(text="Invalid or empty chat_id", status=400)

        chat_id = int(raw_chat_id)
        reply_id = int(raw_reply_to) if raw_reply_to.isdigit() else None

        # Формирование сообщения об оплате
        amount_text = f"\n• <b>Сумма:</b> {html.escape(amount)} ₽" if amount else ""
        text = (
            f"✅ <b>СЧЕТ УСПЕШНО ОПЛАЧЕН</b>\n\n"
            f"• <b>Счет:</b> {html.escape(title)}"
            f"{amount_text}\n"
            f"• <b>Статус:</b> Оплата проведена бухгалтерией 🎉"
        )

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_id,
            allow_sending_without_reply=True
        )

        return web.Response(text="OK", status=200)

    except Exception as e:
        logging.error(f"Ошибка при обработке вебхука оплаты: {e}", exc_info=True)
        return web.Response(text=str(e), status=500)


# ==========================================
# 3. ТОЧКА ВХОДА (Сервер + Polling)
# ==========================================
async def main():
    # Запуск внутреннего веб-сервера на порту 8080
    app = web.Application()
    app.router.add_get("/paid", handle_paid_webhook)
    app.router.add_post("/paid", handle_paid_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logging.info("Веб-сервер вебхуков запущен на порту 8080 (/paid)")

    # Запуск Telegram-бота
    logging.info("Telegram-бот запущен и ожидает файлы...")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())