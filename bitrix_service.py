import base64
import logging
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = (os.getenv("BITRIX24_WEBHOOK_URL") or "").rstrip("/")
ENTITY_TYPE_ID = int(os.getenv("BITRIX24_ENTITY_TYPE_ID", 31))

UF_INVOICE_FILE = os.getenv("UF_INVOICE_FILE", "ufCrm_SMART_INVOICE_1787937924417").strip()
UF_TG_CHAT_ID = os.getenv("UF_TG_CHAT_ID", "ufCrm_SMART_INVOICE_1788010563656").strip()
UF_TG_MSG_ID = os.getenv("UF_TG_MSG_ID", "ufCrm_SMART_INVOICE_1788010580360").strip()


async def upload_file_to_disk(session: aiohttp.ClientSession, file_bytes: bytes, file_name: str) -> int | None:
    """Загружает файл на общий Диск Битрикс24 и возвращает ID файла."""
    try:
        # 1. Получаем список хранилищ
        async with session.post(f"{WEBHOOK_URL}/disk.storage.getlist.json") as resp:
            storage_res = await resp.json()
            storages = storage_res.get("result", [])
            if not storages:
                logging.error("Не удалось найти хранилище на Диске Битрикс24")
                return None
            storage_id = storages[0]["ID"]

        # 2. Загружаем файл в хранилище
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        upload_payload = {
            "id": storage_id,
            "data": {
                "NAME": file_name
            },
            "fileContent": [file_name, file_b64]
        }
        
        async with session.post(f"{WEBHOOK_URL}/disk.storage.uploadfile.json", json=upload_payload) as up_resp:
            upload_res = await up_resp.json()
            file_id = upload_res.get("result", {}).get("ID")
            logging.info(f"📁 Файл успешно загружен на Диск Битрикс24 с ID: {file_id}")
            return file_id
    except Exception as err:
        logging.error(f"Ошибка загрузки на Диск: {err}", exc_info=True)
        return None


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

    title = f"Счет от {user_name} ({file_name})"
    full_comment = f"Отправитель: {user_name} (@{tg_username})\nКомментарий: {comment}"
    
    fields = {
        "title": title,
        "comments": full_comment.replace("\n", "<br>")
    }
    
    if UF_TG_CHAT_ID and chat_id:
        fields[UF_TG_CHAT_ID] = str(chat_id)

    if UF_TG_MSG_ID and message_id:
        fields[UF_TG_MSG_ID] = str(message_id)

    async with aiohttp.ClientSession() as session:
        # Загружаем файл на Диск
        disk_file_id = await upload_file_to_disk(session, file_bytes, file_name)
        
        if disk_file_id and UF_INVOICE_FILE:
            # Для полей диска передается массив идентификаторов вида ["n123"]
            fields[UF_INVOICE_FILE] = [f"n{disk_file_id}"]

        payload = {
            "entityTypeId": ENTITY_TYPE_ID,
            "fields": fields
        }

        logging.info(f"📤 Создание элемента в Битрикс24: {fields}")

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

            domain = WEBHOOK_URL.split("/rest/")[0]
            crm_url = f"{domain}/crm/type/{ENTITY_TYPE_ID}/details/{item_id}/"
            
            return {
                "id": item_id,
                "url": crm_url
            }