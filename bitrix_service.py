import base64
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = (os.getenv("BITRIX24_WEBHOOK_URL") or "").rstrip("/")
ENTITY_TYPE_ID = int(os.getenv("BITRIX24_ENTITY_TYPE_ID", 31))

# Коды кастомных полей из .env
UF_CHAT_ID = os.getenv("UF_TG_CHAT_ID", "ufCrm_TG_CHAT_ID")
UF_MSG_ID = os.getenv("UF_TG_MSG_ID", "ufCrm_TG_MSG_ID")
UF_FILE = os.getenv("UF_INVOICE_FILE", "ufCrm_INVOICE_FILE")

async def create_invoice_in_bitrix(
    file_bytes: bytes,
    file_name: str,
    user_name: str,
    comment: str,
    tg_username: str,
    chat_id: int,
    message_id: int
) -> dict:
    if not WEBHOOK_URL:
        raise ValueError("В файле .env не задан параметр BITRIX24_WEBHOOK_URL")

    file_b64 = base64.b64encode(file_bytes).decode("utf-8")
    
    title = f"Счет от {user_name} ({file_name})"
    full_comment = f"Отправитель: {user_name} (@{tg_username})<br>Чат ID: {chat_id}<br>Сообщение ID: {message_id}<br>Комментарий: {comment}"
    
    fields = {
        "title": title,
        "comments": full_comment,
        UF_CHAT_ID: str(chat_id),
        UF_MSG_ID: str(message_id)
    }

    # Если в CRM настроено поле типа «Файл»
    if UF_FILE:
        fields[UF_FILE] = [file_name, file_b64]
    
    payload = {
        "entityTypeId": ENTITY_TYPE_ID,
        "fields": fields
    }
    
    async with aiohttp.ClientSession() as session:
        url = f"{WEBHOOK_URL}/crm.item.add"
        async with session.post(url, json=payload) as resp:
            result = await resp.json()
            
            if "error" in result:
                raise Exception(f"Bitrix24 API Error: {result.get('error_description', result['error'])}")
            
            item_data = result.get("result", {}).get("item", {})
            item_id = item_data.get("id")
            
            domain = WEBHOOK_URL.split("/rest/")[0]
            crm_url = f"{domain}/crm/type/{ENTITY_TYPE_ID}/details/{item_id}/"
            
            return {
                "id": item_id,
                "url": crm_url
            }