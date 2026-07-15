import asyncio
import threading
import os
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from dotenv import load_dotenv
from chatbot_logic import procesar_mensaje
from database import MotosDAO

# Forzar la carga de variables de entorno
basedir = os.path.dirname(os.path.abspath(__file__))
ruta_env = os.path.join(basedir, ".env")
load_dotenv(dotenv_path=ruta_env)

app = FastAPI(title="Chatbot Motos Webhook API")

# Carga de variables de entorno
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "token_por_defecto_123")
PORT_APP = int(os.getenv("PORT", 8050))

def enviar_mensaje_whatsapp_real(to_wid: str, texto_bot: str):
    """Realiza la petición HTTP POST de salida hacia la API Cloud de Meta."""
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
        # Usamos json=payload para que requests se encargue de la serialización correcta
        response = requests.post(url, json=payload, headers=headers)
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
        enviar_mensaje_whatsapp_real(wid, resultado["texto"])

# --- ENDPOINTS ---

@app.get("/webhook")
def verificar_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        print("✅ Webhook verificado exitosamente.")
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Error de verificación", status_code=403)

@app.post("/webhook")
async def recibir_mensaje_real(request: Request, background_tasks: BackgroundTasks):
    datos = await request.json()
    try:
        entry = datos.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            obj_msg = value["messages"][0]
            contacto = value.get("contacts", [{}])[0]
            wid = f"{obj_msg['from']}@c.us"
            nombre = contacto.get("profile", {}).get("name", "Cliente")
            
            texto_usuario = obj_msg.get("text", {}).get("body", "")
            if not texto_usuario and "interactive" in obj_msg:
                texto_usuario = obj_msg["interactive"]["button_reply"]["title"]
                
            if texto_usuario:
                background_tasks.add_task(manejar_flujo_async, wid, texto_usuario, nombre)
        
    except Exception as e:
        print(f"❌ Error procesando JSON: {e}")
    return {"status": "success"}

# --- SIMULADOR CONSOLA ---

def ejecutar_bucle_simulador():
    asyncio.run(simulador_consola())

async def simulador_consola():
    WID_PRUEBA = "573019998877@c.us"
    NOMBRE_PRUEBA = "Carlos"
    db = MotosDAO()
    db.cerrar_y_crear_nueva_sesion(WID_PRUEBA)
    inicio = await procesar_mensaje(WID_PRUEBA, "", NOMBRE_PRUEBA)
    print(f"\n🤖 Bot: {inicio['texto']}\n")
    while True:
        try:
            msg = input("👤 Tú: ")
            if msg.lower() in ["salir", "exit"]: break
            res = await procesar_mensaje(WID_PRUEBA, msg, NOMBRE_PRUEBA)
            print(f"\n🤖 Bot: {res['texto']}\n")
        except: break

if __name__ == "__main__":
    thread_consola = threading.Thread(target=ejecutar_bucle_simulador, daemon=True)
    thread_consola.start()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_APP)