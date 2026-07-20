import asyncio
import os
import httpx
import hmac
import hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, BackgroundTasks
from dotenv import load_dotenv
from chatbot_logic import procesar_mensaje, verificar_inactividad_proactiva_loop
from database import MotosDAO
from chatwoot_client import ChatwootClient

load_dotenv()

# Carga de variables de entorno
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "token_por_defecto_123")
PORT_APP = int(os.getenv("PORT", 8050))
APP_SECRET = os.getenv("APP_SECRET")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8050")
WEBHOOK_META_PATH = os.getenv("WEBHOOK_META_PATH", "/webhook")
if not WEBHOOK_META_PATH.startswith("/"):
    WEBHOOK_META_PATH = "/" + WEBHOOK_META_PATH

WEBHOOK_CHATWOOT_PATH = os.getenv("WEBHOOK_CHATWOOT_PATH", "/webhook/chatwoot")
if not WEBHOOK_CHATWOOT_PATH.startswith("/"):
    WEBHOOK_CHATWOOT_PATH = "/" + WEBHOOK_CHATWOOT_PATH

async def verificar_firma(request: Request) -> bool:
    """Verifica que la petición provenga realmente de los servidores de Meta."""
    if not APP_SECRET:
        # Permitir pasar si no está configurado en el .env (por ejemplo en local o desarrollo)
        return True
    firma_cabecera = request.headers.get("X-Hub-Signature-256")
    if not firma_cabecera or not firma_cabecera.startswith("sha256="):
        return False
    sha_recibido = firma_cabecera.split("=")[1]
    cuerpo = await request.body()
    sha_calculado = hmac.new(
        APP_SECRET.encode("utf-8"),
        cuerpo,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sha_calculado, sha_recibido)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🔗 Webhook Meta activo en: {BASE_URL}{WEBHOOK_META_PATH}")
    print(f"🔗 Webhook Chatwoot activo en: {BASE_URL}{WEBHOOK_CHATWOOT_PATH}")
    
    tarea_motor = asyncio.create_task(verificar_inactividad_proactiva_loop(enviar_mensaje_whatsapp_real))
    
    yield
    
    tarea_motor.cancel()

app = FastAPI(title="Chatbot Motos Webhook API", lifespan=lifespan)

async def enviar_mensaje_whatsapp_real(to_wid: str, texto_bot: str):
    """Realiza la petición HTTP POST de salida hacia la API Cloud de Meta de forma asíncrona."""
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("⚠️ Advertencia: Credenciales no configuradas en el .env")
        return

    # Limpiar ID para Meta
    wid_limpio = to_wid.replace("@c.us", "")

    # URL actualizada a v25.0 según sugerencia de la API de Meta
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}", 
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": wid_limpio,
        "type": "text",
        "text": {"body": texto_bot}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"❌ Error API WhatsApp Meta Saliente ({response.status_code}): {response.text}")
            else:
                print(f"📤 Respuesta enviada exitosamente a: {wid_limpio}")
    except Exception as e:
        print(f"❌ Error crítico en la petición HTTP saliente: {e}")

async def manejar_flujo_async(wid: str, mensaje: str, nombre: str):
    """Procesamiento en background para no bloquear el Webhook."""
    resultado = await procesar_mensaje(wid, mensaje, nombre)
    if resultado and "texto" in resultado:
        # 1. Enviar respuesta al cliente
        await enviar_mensaje_whatsapp_real(wid, resultado["texto"])
        
        # 2. Si el lead fue calificado y necesita agente, integrarlo con Chatwoot y notificar
        if resultado.get("necesita_agente"):
            db = MotosDAO()
            cliente = await asyncio.to_thread(db.obtener_cliente, wid)
            if cliente:
                wid_limpio = wid.replace("@c.us", "")
                enlace_chat = f"https://wa.me/{wid_limpio}"
                
                info_adicional = ""
                if cliente.get("gasto_transporte"):
                    info_adicional = (
                        f"\n📍 *Ciudad:* {cliente.get('ciudad', '').title()}"
                        f"\n💳 *Cupo Recibo:* {cliente.get('tipo_cupo')}"
                        f"\n🚌 *Gasto Transporte:* {cliente.get('gasto_transporte')}"
                    )
                elif cliente.get("tiempo_entrega"):
                    info_adicional = (
                        f"\n📍 *Ciudad:* {cliente.get('ciudad', '').title()}"
                        f"\n💳 *Cupo Recibo:* {cliente.get('tipo_cupo')}"
                        f"\n⏱️ *Tiempo Entrega:* {cliente.get('tiempo_entrega')}"
                    )
                    
                msg_asesor = (
                    f"🔔 *¡NUEVO LEAD CALIFICADO!*\n\n"
                    f"👤 *Cliente:* {cliente.get('nombre', nombre)}\n"
                    f"📱 *Numero:* {wid_limpio}"
                    f"{info_adicional}\n\n"
                    f"💬 *Chat Directo:* {enlace_chat}"
                )
                
                # --- INTEGRACIÓN CON CHATWOOT ---
                chatwoot = ChatwootClient()
                contact_id = await chatwoot.buscar_o_crear_contacto(wid, cliente.get('nombre', nombre))
                if contact_id:
                    conv_id = await chatwoot.crear_conversacion(contact_id)
                    if conv_id:
                        await chatwoot.enviar_nota_privada(conv_id, msg_asesor)

                # Cambiar a estado ATENCION_MANUAL para silenciar el bot mientras el humano atiende
                await asyncio.to_thread(db.guardar_progreso_cliente, wid, estado="ATENCION_MANUAL")
                print(f"🤝 [HANDOVER] Lead {wid} derivado a Chatwoot y puesto en ATENCION_MANUAL.")

                # Notificar adicionalmente al WhatsApp personal del asesor si está configurado
                asesor_number = os.getenv("ASESOR_NUMBER")
                if asesor_number:
                    print(f"📞 [NOTIFICACIÓN ASESOR] Notificando nuevo lead al asesor comercial: {asesor_number}")
                    await enviar_mensaje_whatsapp_real(f"{asesor_number}@c.us", msg_asesor)

async def manejar_flujo_chatwoot_async(wid: str, mensaje: str, nombre: str, conversation_id: Optional[int]):
    """Procesamiento en background para mensajes provenientes de Chatwoot."""
    resultado = await procesar_mensaje(wid, mensaje, nombre)
    if resultado and "texto" in resultado:
        texto_bot = resultado["texto"]
        
        # 1. Enviar respuesta saliente del bot a Chatwoot si se dispone de conversation_id
        if conversation_id:
            chatwoot = ChatwootClient()
            await chatwoot.enviar_mensaje_bot(conversation_id, texto_bot)
        else:
            await enviar_mensaje_whatsapp_real(wid, texto_bot)
            
        # 2. Si el lead califica y requiere atención humana
        if resultado.get("necesita_agente"):
            db = MotosDAO()
            cliente = await asyncio.to_thread(db.obtener_cliente, wid)
            if cliente:
                wid_limpio = wid.replace("@c.us", "")
                enlace_chat = f"https://wa.me/{wid_limpio}"
                
                info_adicional = ""
                if cliente.get("gasto_transporte"):
                    info_adicional = (
                        f"\n📍 *Ciudad:* {cliente.get('ciudad', '').title()}"
                        f"\n💳 *Cupo Recibo:* {cliente.get('tipo_cupo')}"
                        f"\n🚌 *Gasto Transporte:* {cliente.get('gasto_transporte')}"
                    )
                elif cliente.get("tiempo_entrega"):
                    info_adicional = (
                        f"\n📍 *Ciudad:* {cliente.get('ciudad', '').title()}"
                        f"\n💳 *Cupo Recibo:* {cliente.get('tipo_cupo')}"
                        f"\n⏱️ *Tiempo Entrega:* {cliente.get('tiempo_entrega')}"
                    )
                    
                msg_asesor = (
                    f"🔔 *¡NUEVO LEAD CALIFICADO!*\n\n"
                    f"👤 *Cliente:* {cliente.get('nombre', nombre)}\n"
                    f"📱 *Numero:* {wid_limpio}"
                    f"{info_adicional}\n\n"
                    f"💬 *Chat Directo:* {enlace_chat}"
                )
                
                if conversation_id:
                    chatwoot = ChatwootClient()
                    await chatwoot.enviar_nota_privada(conversation_id, msg_asesor)

                await asyncio.to_thread(db.guardar_progreso_cliente, wid, estado="ATENCION_MANUAL")
                print(f"🤝 [HANDOVER] Lead {wid} derivado a Chatwoot y puesto en ATENCION_MANUAL.")

                asesor_number = os.getenv("ASESOR_NUMBER")
                if asesor_number:
                    print(f"📞 [NOTIFICACIÓN ASESOR] Notificando nuevo lead al asesor comercial: {asesor_number}")
                    await enviar_mensaje_whatsapp_real(f"{asesor_number}@c.us", msg_asesor)

# --- ENDPOINTS ---

@app.get("/")
def leer_ruta():
    return {"status": "ok", "mensaje": "Motor Smarthouse-Bot Activo"}

@app.get("/webhook")
@app.get("/webhook/")
@app.get(WEBHOOK_META_PATH)
@app.get(f"{WEBHOOK_META_PATH}/")
def verificar_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        print("✅ Webhook verificado exitosamente.")
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Error de verificación", status_code=403)

@app.post("/webhook")
@app.post("/webhook/")
@app.post(WEBHOOK_META_PATH)
@app.post(f"{WEBHOOK_META_PATH}/")
async def recibir_mensaje_real(request: Request, background_tasks: BackgroundTasks):
    if not await verificar_firma(request):
        return Response(content="Firma de webhook inválida", status_code=401)

    try:
        datos = await request.json()
        
        # Soporte para payload directo de BuilderBot
        if "from" in datos and "body" in datos and "entry" not in datos:
            from_num = str(datos["from"])
            wid = f"{from_num}@c.us" if not from_num.endswith("@c.us") else from_num
            nombre = datos.get("name", datos.get("pushName", "Cliente"))
            texto_usuario = datos.get("body", "")
            if texto_usuario:
                background_tasks.add_task(manejar_flujo_async, wid, texto_usuario, nombre)
                return {"status": "success"}

        entries = datos.get("entry", [])
        if not entries:
            return {"status": "no entries"}
        entry = entries[0]
        
        changes = entry.get("changes", [])
        if not changes:
            return {"status": "no changes"}
        change = changes[0]
        
        value = change.get("value", {})
        
        if "messages" in value:
            messages = value.get("messages", [])
            if not messages:
                return {"status": "no messages"}
            obj_msg = messages[0]
            
            contacts = value.get("contacts", [])
            contacto = contacts[0] if contacts else {}
            
            wid = f"{obj_msg['from']}@c.us"
            nombre = contacto.get("profile", {}).get("name", "Cliente")
            
            texto_usuario = obj_msg.get("text", {}).get("body", "")
            if not texto_usuario and "interactive" in obj_msg:
                interactive = obj_msg["interactive"]
                if "button_reply" in interactive:
                    texto_usuario = interactive["button_reply"]["title"]
                elif "list_reply" in interactive:
                    texto_usuario = interactive["list_reply"]["title"]
                
            if texto_usuario:
                background_tasks.add_task(manejar_flujo_async, wid, texto_usuario, nombre)
        
    except Exception as e:
        print(f"❌ Error procesando JSON: {e}")
    return {"status": "success"}

@app.post("/webhook/chatwoot")
@app.post("/webhook/chatwoot/")
@app.post(WEBHOOK_CHATWOOT_PATH)
@app.post(f"{WEBHOOK_CHATWOOT_PATH}/")
async def recibir_webhook_chatwoot(request: Request, background_tasks: BackgroundTasks):
    """Escucha eventos de Chatwoot (mensajes entrantes y resolución) para ejecutar el chatbot."""
    try:
        datos = await request.json()
        event = datos.get("event")

        # 1. Eventos de resolución o cambio de estado para reactivar el bot
        if event in ("conversation_resolved", "conversation_status_changed"):
            meta = datos.get("meta", {})
            sender = datos.get("sender", {})
            phone_number = sender.get("phone_number") or meta.get("sender", {}).get("phone_number")
            
            if not phone_number and "conversation" in datos:
                conv = datos["conversation"]
                phone_number = conv.get("meta", {}).get("sender", {}).get("phone_number")

            if phone_number:
                wid_limpio = phone_number.replace("+", "").replace("@c.us", "")
                wid = f"{wid_limpio}@c.us"
                
                estado_nuevo = datos.get("status") or datos.get("conversation", {}).get("status")
                if event == "conversation_resolved" or estado_nuevo == "resolved":
                    db = MotosDAO()
                    await asyncio.to_thread(db.cerrar_y_crear_nueva_sesion, wid)
                    await asyncio.to_thread(db.guardar_progreso_cliente, wid, estado="INICIO")
                    print(f"🔄 [CHATWOOT WEBHOOK] Conversación resuelta en Chatwoot para {wid}. Bot reactivado en estado INICIO.")
            return {"status": "success"}

        # 2. Filtrado inicial de mensajes entrantes del usuario
        if event == "message_created":
            message_type = datos.get("message_type")
            is_private = datos.get("private", False)
            content = (datos.get("content") or "").strip()

            # Procesar únicamente si es mensaje entrante del usuario (incoming), no es nota privada y tiene texto
            if message_type == "incoming" and not is_private and content:
                conversation = datos.get("conversation", {})
                conversation_id = conversation.get("id") or datos.get("conversation_id")
                
                sender = datos.get("sender", {})
                phone_number = sender.get("phone_number")
                nombre = sender.get("name") or "Cliente"

                if not phone_number and "meta" in conversation:
                    phone_number = conversation["meta"].get("sender", {}).get("phone_number")

                if phone_number:
                    wid_limpio = phone_number.replace("+", "").replace("@c.us", "")
                    wid = f"{wid_limpio}@c.us"

                    # Control de Handover: Verificar si la conversación está asignada a un agente o en atención humana
                    assignee = conversation.get("assignee") or conversation.get("meta", {}).get("assignee")
                    status = conversation.get("status")
                    
                    db = MotosDAO()
                    cliente = await asyncio.to_thread(db.obtener_cliente, wid)

                    # Si el cliente ya está en ATENCION_MANUAL en BD o asignado a un agente en Chatwoot
                    if (cliente and cliente.get("estado") == "ATENCION_MANUAL") or (assignee is not None and status != "pending"):
                        print(f"🤫 [SILENCIO CHATWOOT] Cliente {wid} en atención humana o asignado a un agente.")
                        return {"status": "ignored_handover"}

                    # Ejecutar el motor conversacional en background enviando respuesta a Chatwoot
                    background_tasks.add_task(manejar_flujo_chatwoot_async, wid, content, nombre, conversation_id)

    except Exception as e:
        print(f"❌ Error procesando webhook de Chatwoot: {e}")
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT_APP, reload=False)