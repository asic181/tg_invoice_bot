import base64
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = (os.getenv("BITRIX24_WEBHOOK_URL") or "").rstrip("/")
ENTITY_TYPE_ID = int(os.getenv("BITRIX24_ENTITY_TYPE_ID", 31))

UF_INVOICE_FILE = os.getenv("UF_INVOICE_FILE", "ufCrm_SMART_INVOICE_1787937924417")
UF_TG_CHAT_ID = os.getenv("UF_TG_CHAT_ID")
UF_TG_MSG_ID = os.getenv("UF_TG_MSG_ID")

async def create_invoice_in_bitrix(
    file_bytes: bytes,
    file_name: str,
    user_name: str,
    comment: str,
    tg_username: str,
    chat_id: int,
    message_id: int,
    amount: float = 0.0
) -> dict:
    if not WEBHOOK_URL:
        raise ValueError("В файле .env не задан параметр BITRIX24_WEBHOOK_URL")

    file_b64 = base64.b64encode(file_bytes).decode("utf-8")
    
    title = f"Счет от {user_name} ({file_name})"
    full_comment = f"Отправитель: {user_name} (@{tg_username})<br>Комментарий: {comment}"
    
    fields = {
        "title": title,
        "comments": full_comment,
        "opportunity": amount,
        "isManualOpportunity": "Y" if amount > 0 else "N",
        "currencyId": "RUB",
    }

    # Записываем файл
    if UF_INVOICE_FILE:
        fields[UF_INVOICE_FILE] = [file_name, file_b64]

    # Записываем данные для обратной связи в отдельные поля
    if UF_TG_CHAT_ID:
        fields[UF_TG_CHAT_ID] = str(chat_id)
    if UF_TG_MSG_ID:
        fields[UF_TG_MSG_ID] = str(message_id)
    
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