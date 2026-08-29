import base64
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = (os.getenv("BITRIX24_WEBHOOK_URL") or "").rstrip("/")
ENTITY_TYPE_ID = int(os.getenv("BITRIX24_ENTITY_TYPE_ID", 31))

# Пользовательские поля
UF_INVOICE_FILE = os.getenv("UF_INVOICE_FILE")
UF_TG_CHAT_ID = os.getenv("UF_TG_CHAT_ID")
UF_TG_MSG_ID = os.getenv("UF_TG_MSG_ID")

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
    
    fields = {
        "title": title,
        "comments": full_comment.replace("\n", "<br>")
    }
    
    # Привязка файла к пользовательскому полю
    if UF_INVOICE_FILE:
        fields[UF_INVOICE_FILE] = {
            "fileData": [file_name, file_b64]
        }
    else:
        # Резервный вариант, если UF_INVOICE_FILE не задан
        fields["fileData"] = [file_name, file_b64]

    # Запись ID чата и сообщения
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