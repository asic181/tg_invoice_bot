import base64
import logging
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = (os.getenv("BITRIX24_WEBHOOK_URL") or "").rstrip("/")
ENTITY_TYPE_ID = int(os.getenv("BITRIX24_ENTITY_TYPE_ID", 31))

# Точные системные имена полей
UF_INVOICE_FILE = os.getenv("UF_INVOICE_FILE", "ufCrm_SMART_INVOICE_1787937924417").strip()
UF_TG_CHAT_ID = os.getenv("UF_TG_CHAT_ID", "ufCrm_SMART_INVOICE_1788010563656").strip()
UF_TG_MSG_ID = os.getenv("UF_TG_MSG_ID", "ufCrm_SMART_INVOICE_1788010580360").strip()


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
        raise ValueError("В файле .env не задан параметр BITRIX24_WEBHOOK_URL")

    file_b64 = base64.b64encode(file_bytes).decode("utf-8")
    
    title = f"Счет от {user_name} ({file_name})"
    full_comment = f"Отправитель: {user_name} (@{tg_username})\nКомментарий: {comment}"
    
    # Формируем поля элемента
    fields = {
        "title": title,
        "comments": full_comment.replace("\n", "<br>"),
        # Передаем файл напрямую в кастомное поле
        UF_INVOICE_FILE: {
            "fileData": [file_name, file_b64]
        }
    }
    
    if UF_TG_CHAT_ID and chat_id:
        fields[UF_TG_CHAT_ID] = str(chat_id)

    if UF_TG_MSG_ID and message_id:
        fields[UF_TG_MSG_ID] = str(message_id)
    
    payload = {
        "entityTypeId": ENTITY_TYPE_ID,
        "fields": fields
    }

    async with aiohttp.ClientSession() as session:
        url = f"{WEBHOOK_URL}/crm.item.add.json"
        async with session.post(url, json=payload) as resp:
            status_code = resp.status
            result = await resp.json()
            
            logging.info(f"📥 Ответ crm.item.add (HTTP {status_code}): {result}")
            
            if "error" in result:
                logging.error(f"❌ Ошибка Битрикс24: {result}")
                raise Exception(f"Bitrix24 API Error: {result.get('error_description', result['error'])}")
            
            item_data = result.get("result", {}).get("item", {})
            item_id = item_data.get("id")

            # Если поле файла не заполнилось (например, поле множественное), пробуем передать массивом через update
            if not item_data.get(UF_INVOICE_FILE):
                logging.info(f"Поле файла пустое, пробуем обновление через crm.item.update (массивом)...")
                update_payload = {
                    "entityTypeId": ENTITY_TYPE_ID,
                    "id": item_id,
                    "fields": {
                        UF_INVOICE_FILE: [
                            {"fileData": [file_name, file_b64]}
                        ]
                    }
                }
                async with session.post(f"{WEBHOOK_URL}/crm.item.update.json", json=update_payload) as up_resp:
                    up_result = await up_resp.json()
                    logging.info(f"📥 Ответ crm.item.update: {up_result}")

            domain = WEBHOOK_URL.split("/rest/")[0]
            crm_url = f"{domain}/crm/type/{ENTITY_TYPE_ID}/details/{item_id}/"
            
            return {
                "id": item_id,
                "url": crm_url
            }