import base64
import logging
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = (os.getenv("BITRIX24_WEBHOOK_URL") or "").rstrip("/")[cite: 4]
ENTITY_TYPE_ID = int(os.getenv("BITRIX24_ENTITY_TYPE_ID", 31))[cite: 4]

UF_TG_CHAT_ID = os.getenv("UF_TG_CHAT_ID", "").strip()
UF_TG_MSG_ID = os.getenv("UF_TG_MSG_ID", "").strip()


async def create_invoice_in_bitrix(
    file_bytes: bytes,
    file_name: str,
    user_name: str,
    comment: str,
    tg_username: str,
    chat_id: int | str = None,
    message_id: int | str = None
) -> dict:
    if not WEBHOOK_URL:
        raise ValueError("В файле .env не задан параметр BITRIX24_WEBHOOK_URL")[cite: 4]

    file_b64 = base64.b64encode(file_bytes).decode("utf-8")[cite: 4]
    
    title = f"Счет от {user_name} ({file_name})"[cite: 4]
    full_comment = f"Отправитель: {user_name} (@{tg_username})\nКомментарий: {comment}"[cite: 4]
    
    fields = {
        "title": title,[cite: 4]
        "comments": full_comment.replace("\n", "<br>"),[cite: 4]
        "fileData": [file_name, file_b64][cite: 4]
    }
    
    # Логируем кастомные поля перед записью
    logging.info(f"⚙️ Проверка UF-полей из .env -> UF_TG_CHAT_ID='{UF_TG_CHAT_ID}', UF_TG_MSG_ID='{UF_TG_MSG_ID}'")

    if UF_TG_CHAT_ID and chat_id:
        fields[UF_TG_CHAT_ID] = str(chat_id)
        logging.info(f"➕ Добавлено поле Chat ID [{UF_TG_CHAT_ID}] = {chat_id}")
    elif not UF_TG_CHAT_ID:
        logging.warning("⚠️ Переменная UF_TG_CHAT_ID не задана в .env!")

    if UF_TG_MSG_ID and message_id:
        fields[UF_TG_MSG_ID] = str(message_id)
        logging.info(f"➕ Добавлено поле Msg ID [{UF_TG_MSG_ID}] = {message_id}")
    elif not UF_TG_MSG_ID:
        logging.warning("⚠️ Переменная UF_TG_MSG_ID не задана в .env!")
    
    payload = {
        "entityTypeId": ENTITY_TYPE_ID,[cite: 4]
        "fields": fields
    }
    
    # Маскируем base64 для читаемости лога
    fields_for_log = dict(fields)
    fields_for_log["fileData"] = [file_name, f"<{len(file_bytes)} bytes b64>"]
    logging.info(f"📤 Отправка запроса в Битрикс24 (entityTypeId={ENTITY_TYPE_ID}): {fields_for_log}")

    async with aiohttp.ClientSession() as session:
        url = f"{WEBHOOK_URL}/crm.item.add.json"[cite: 4]
        async with session.post(url, json=payload) as resp:[cite: 4]
            status_code = resp.status
            result = await resp.json()[cite: 4]
            
            logging.info(f"📥 Ответ от Битрикс24 (HTTP {status_code}): {result}")
            
            if "error" in result:
                logging.error(f"❌ Ошибка Битрикс24: {result}")
                raise Exception(f"Bitrix24 API Error: {result.get('error_description', result['error'])}")[cite: 4]
            
            item_data = result.get("result", {}).get("item", {})[cite: 4]
            item_id = item_data.get("id")[cite: 4]
            
            logging.info(f"✅ Карточка успешно создана! ID: {item_id}, Сохранённые поля Битрикс: {item_data}")
            
            domain = WEBHOOK_URL.split("/rest/")[0][cite: 4]
            crm_url = f"{domain}/crm/type/{ENTITY_TYPE_ID}/details/{item_id}/"[cite: 4]
            
            return {
                "id": item_id,[cite: 4]
                "url": crm_url[cite: 4]
            }