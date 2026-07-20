# chatwoot_client.py
import os
import httpx
from typing import Optional, Dict, Any

CHATWOOT_URL = os.getenv("CHATWOOT_URL", "").rstrip("/")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_TOKEN = os.getenv("CHATWOOT_BOT_TOKEN") or os.getenv("CHATWOOT_TOKEN", "")
CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID", "1")

class ChatwootClient:
    def __init__(self):
        self.base_url = CHATWOOT_URL
        self.account_id = CHATWOOT_ACCOUNT_ID
        self.token = CHATWOOT_TOKEN
        self.inbox_id = int(CHATWOOT_INBOX_ID) if CHATWOOT_INBOX_ID.isdigit() else 1

    def _headers() -> Dict[str, str]:
        return {
            "api_access_token": CHATWOOT_TOKEN,
            "Content-Type": "application/json"
        }

    async def buscar_o_crear_contacto(self, phone_number: str, name: str) -> Optional[int]:
        """Busca un contacto por su número telefónico en Chatwoot o lo crea si no existe."""
        if not self.base_url or not self.token:
            print("⚠️ Chatwoot no configurado (CHATWOOT_URL o CHATWOOT_TOKEN ausentes).")
            return None

        clean_phone = phone_number.replace("@c.us", "").replace("+", "")
        formatted_phone = f"+{clean_phone}"

        search_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/search"
        headers = self._headers()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Buscar contacto existente
                res = await client.get(search_url, params={"q": clean_phone}, headers=headers)
                if res.status_code == 200:
                    payload = res.json()
                    payload_data = payload.get("payload", [])
                    if payload_data:
                        contact_id = payload_data[0].get("id")
                        print(f"👤 [CHATWOOT] Contacto encontrado: ID {contact_id}")
                        return contact_id

                # 2. Si no existe, crear contacto
                create_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts"
                contact_payload = {
                    "name": name or "Cliente WhatsApp",
                    "phone_number": formatted_phone
                }
                res_create = await client.post(create_url, json=contact_payload, headers=headers)
                if res_create.status_code in (200, 201):
                    new_contact = res_create.json().get("payload", {}).get("contact", {})
                    contact_id = new_contact.get("id")
                    print(f"✅ [CHATWOOT] Nuevo contacto creado: ID {contact_id}")
                    return contact_id
                else:
                    print(f"❌ Error creando contacto en Chatwoot ({res_create.status_code}): {res_create.text}")
        except Exception as e:
            print(f"❌ Error de comunicación con Chatwoot en buscar_o_crear_contacto: {e}")
        return None

    async def crear_conversacion(self, contact_id: int) -> Optional[int]:
        """Crea una conversación en el Inbox especificado de Chatwoot."""
        if not self.base_url or not self.token or not contact_id:
            return None

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations"
        headers = self._headers()
        payload = {
            "source_id": str(contact_id),
            "inbox_id": self.inbox_id,
            "contact_id": contact_id,
            "status": "open"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code in (200, 201):
                    conv_id = res.json().get("id")
                    print(f"💬 [CHATWOOT] Conversación abierta: ID {conv_id}")
                    return conv_id
                else:
                    print(f"❌ Error creando conversación en Chatwoot ({res_status:=res.status_code}): {res.text}")
        except Exception as e:
            print(f"❌ Error abriendo conversación en Chatwoot: {e}")
        return None

    async def enviar_nota_privada(self, conversation_id: int, content: str) -> bool:
        """Adjunta una nota privada dentro de la conversación para el equipo comercial."""
        if not self.base_url or not self.token or not conversation_id:
            return False

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        headers = self._headers()
        payload = {
            "content": content,
            "message_type": "outgoing",
            "private": True
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code in (200, 201):
                    print(f"📝 [CHATWOOT] Nota privada enviada a conversación {conversation_id}")
                    return True
                else:
                    print(f"❌ Error enviando nota privada en Chatwoot ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"❌ Error creando nota privada en Chatwoot: {e}")
        return False

    async def enviar_mensaje_bot(self, conversation_id: int, content: str) -> bool:
        """Envía una respuesta saliente pública del bot a la conversación de Chatwoot."""
        if not self.base_url or not self.token or not conversation_id:
            return False

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        headers = self._headers()
        payload = {
            "content": content,
            "message_type": "outgoing",
            "private": False
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code in (200, 201):
                    print(f"📤 [CHATWOOT BOT] Mensaje del bot enviado a conversación {conversation_id}")
                    return True
                else:
                    print(f"❌ Error enviando mensaje del bot a Chatwoot ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"❌ Error enviando mensaje del bot a Chatwoot: {e}")
        return False
