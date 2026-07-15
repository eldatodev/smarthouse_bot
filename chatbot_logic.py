# chatbot_logic.py
import re
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
import ollama
from database import MotosDAO

# =====================================================================
# CONFIGURACIÓN Y CONSTANTES DE COBERTURA (BARRANQUILLA Y ATLÁNTICO)
# =====================================================================
CIUDADES_VALIDAS = [
    "barranquilla", "atlantico", "soledad", "malambo", "galapa",
    "puerto colombia", "puerto", "juan de acosta", "tubara",
    "piojo", "repelon", "sabanagrande", "sabanalarga", "santo tomas",
    "suan", "luruaco", "baranoa", "candelaria", "usiacuri", 
    "campo de la cruz", "campo", "ponedera", "palmar de varela", "manati", "santa lucia"
]

RESET_KEYWORDS = {"reiniciar", "reset", "empezar de nuevo", "volver a empezar", "inicio"}

MODELO_IA = "llama3.2:1b"  # Modelo ligero optimizado para CPU/RAM locales
TIMEOUT_INACTIVIDAD = timedelta(hours=2)  # Tiempo límite pasivo para reiniciar hilos muertos

# =====================================================================
# MOTOR DE RESPUESTAS DIRECTAS (MÁXIMA CONFIABILIDAD Y CERO ALUCINACIONES)
# =====================================================================
def _obtener_respuesta_comercial(mensaje_usuario: str, guion_fijo: str) -> str:
    """
    Retorna directamente el guión comercial preestablecido.
    Garantiza que el cliente reciba la información exacta de la campaña sin desvíos de la IA.
    """
    return guion_fijo


# =====================================================================
# EXTRACCIÓN INTELIGENTE DE DATOS CON FILTROS HÍBRIDOS (PYTHON + OLLAMA)
# =====================================================================

async def _extraer_ciudad_con_ollama(texto_usuario: str) -> Optional[str]:
    if not texto_usuario or not texto_usuario.strip():
        return None

    # [FILTRO PYTHON] Coincidencia directa para evitar mutilaciones del modelo de 1B
    texto_lc = texto_usuario.lower()
    for ciudad in CIUDADES_VALIDAS:
        if ciudad in texto_lc:
            print(f"   [Filtro Python] Coincidencia directa encontrada para: '{ciudad}'")
            return ciudad

    # Procesamiento con IA para textos enredados
    prompt = f"""
    Analiza el siguiente texto y dime qué municipio del Atlántico menciona.
    Responde ÚNICAMENTE con la palabra clave del municipio en minúsculas. 
    Si no menciona ninguno, responde strictly "ninguna". No agregues saludos ni puntuación.

    Texto: "{texto_usuario}"
    Municipio:"""
    try:
        response = ollama.generate(model=MODELO_IA, prompt=prompt, options={"temperature": 0.0, "top_p": 0.1, "num_predict": 10})
        detectada = response['response'].strip().lower().replace(".", "").replace("\n", "").replace("\r", "")
        
        print(f"   [DEBUG OLLAMA] Entrada: '{texto_usuario}' -> {MODELO_IA} extrajo Ciudad: '{detectada}'")
        
        for ciudad in CIUDADES_VALIDAS:
            if ciudad in detectada or detectada in ciudad:
                return ciudad
        return None
    except Exception as e:
        print(f"❌ Error en Ollama Ciudad: {e}")
        return None


async def _clasificar_transporte_con_ollama(texto_usuario: str) -> Optional[str]:
    if not texto_usuario or not texto_usuario.strip():
        return None

    # Normalizamos la cadena para facilitar las búsquedas exactas por código
    texto_lc = texto_usuario.lower().replace(".", "").replace(" ", "")

    # =====================================================================
    # [FILTRO PYTHON] Extracción matemática directa y textual para romper bucles
    # =====================================================================
    # 1. Detectar rangos altos por palabras clave explícitas (+20k)
    if "20" in texto_lc and ("mas" in texto_lc or "más" in texto_usuario.lower() or ">" in texto_lc):
        print("   [Filtro Python] Coincidencia directa encontrada: '+20k'")
        return "+20k"
    
    # 2. Detectar si digitan números directos (ej: 30 mil, 25 mil, 40, 12000)
    numeros = re.findall(r'\d+', texto_lc)
    if numeros:
        primer_numero = int(numeros[0])
        # Si digitan el valor completo ej: 30000 o 15000, tomamos los primeros dos dígitos
        if primer_numero >= 1000:
            primer_numero = int(str(primer_numero)[:2])
            
        if primer_numero >= 20:
            print(f"   [Filtro Python] Número extraído {primer_numero}k -> Clasificado como: '+20k'")
            return "+20k"
        elif 15 <= primer_numero < 20:
            print(f"   [Filtro Python] Número extraído {primer_numero}k -> Clasificado como: '15k-20k'")
            return "15k-20k"
        elif 10 <= primer_numero < 15:
            print(f"   [Filtro Python] Número extraído {primer_numero}k -> Clasificado como: '10k-15k'")
            return "10k-15k"

    # 3. Detectar clics en los botones del cliente o textos literales sencillos
    if "10" in texto_lc and "15" in texto_lc: return "10k-15k"
    if "15" in texto_lc and "20" in texto_lc: return "15k-20k"
    if "20" in texto_lc: return "+20k"

    # =====================================================================
    # RESPALDO CON IA (Solo si las reglas fijas previas fallan por completo)
    # =====================================================================
    prompt = f"""
    Clasifica el gasto diario en transporte del usuario en una de estas tres etiquetas exactas: "10k-15k", "15k-20k" o "+20k".
    Responde ÚNICAMENTE con la etiqueta seleccionada. Si no se entiende o no menciona montos, responde "desconocido".

    Texto: "{texto_usuario}"
    Resultado:"""
    try:
        response = ollama.generate(model=MODELO_IA, prompt=prompt)
        res = response['response'].strip().replace(".", "").replace("\n", "").replace("\r", "").lower()
        
        print(f"   [DEBUG OLLAMA] Entrada: '{texto_usuario}' -> {MODELO_IA} clasificó Gasto: '{res}'")
        
        if "10k-15k" in res: return "10k-15k"
        if "15k-20k" in res: return "15k-20k"
        if "+20k" in res or "20" in res: return "+20k"
        return None
    except Exception as e:
        print(f"❌ Error en Ollama Transporte: {e}")
        return None


async def _detectar_afirmacion_con_ollama(texto_usuario: str) -> bool:
    if not texto_usuario or not texto_usuario.strip():
        return False

    prompt = f"""
    ¿El usuario afirma que SÍ está reportado en centrales de riesgo, Datacrédito o que tiene deudas castigadas? 
    Responde estrictamente con la palabra SI o la palabra NO. No agregues explicaciones de ningún tipo.

    Texto: "{texto_usuario}"
    Resultado:"""
    try:
        response = ollama.generate(model=MODELO_IA, prompt=prompt)
        res = response['response'].strip().upper().replace(".", "").replace("\n", "").replace("\r", "")
        
        print(f"   [DEBUG OLLAMA] Entrada: '{texto_usuario}' -> {MODELO_IA} detectó Reporte: '{res}'")
        return "SI" in res
    except Exception as e:
        print(f"❌ Error en Ollama Reporte: {e}")
        return False


# =====================================================================
# PROCESAMIENTO RECOLECTOR/REACTIVO (ENTRADA DE WEBHOOKS)
# =====================================================================
async def procesar_mensaje(wid: str, mensaje_usuario: Optional[str], nombre_wa: str) -> Dict[str, Any]:
    db = MotosDAO()
    cliente: Optional[Dict[str, Any]] = db.obtener_cliente(wid)
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not cliente:
        db.guardar_progreso_cliente(wid, nombre=nombre_wa, estado="INICIO", ultima_interaccion=ahora_str)
        cliente = db.obtener_cliente(wid)

    texto_input = (mensaje_usuario or "").strip()
    estados_finales = ["RECHAZADO", "TIEMPO_ENTREGA", "BRILLA_DILO"]

    # --- CONTROL DE INACTIVIDAD PASIVO (TIMEOUT DE SESIÓN) ---
    if cliente.get('ultima_interaccion') and cliente['estado'] not in estados_finales:
        try:
            ultima_vez = datetime.strptime(cliente['ultima_interaccion'], "%Y-%m-%d %H:%M:%S")
            if datetime.now() - ultima_vez > TIMEOUT_INACTIVIDAD:
                print(f"⏱️ [TIMEOUT PASIVO] {wid} superó las 2 horas. Reiniciando sesión.")
                db.cerrar_y_crear_nueva_sesion(wid)
                db.guardar_progreso_cliente(wid, nombre=nombre_wa, estado="INICIO", ultima_interaccion=ahora_str)
                cliente = db.obtener_cliente(wid)
        except ValueError:
            pass

    # Actualizar estampa de tiempo de la interacción entrante
    db.guardar_progreso_cliente(wid, ultima_interaccion=ahora_str)
    estado_actual = cliente['estado']

    if any(keyword in texto_input.lower() for keyword in RESET_KEYWORDS):
        db.cerrar_y_crear_nueva_sesion(wid)
        db.guardar_progreso_cliente(wid, nombre=nombre_wa, estado="INICIO", ultima_interaccion=ahora_str)
        return {"texto": "Listo, empecemos de nuevo. ¿En qué ciudad te encuentras?"}

    # --- ESTADO: INICIO ---
    if estado_actual == "INICIO":
        if not texto_input:
            return {"texto": "¡Hola! Para empezar, cuéntame en qué ciudad te encuentras. 🏍️"}

        ciudad_detectada = await _extraer_ciudad_con_ollama(texto_input)
        if ciudad_detectada:
            db.guardar_progreso_cliente(wid, ciudad=ciudad_detectada, estado="TIPO_CUPO")
            guion = f"¡Perfecto! Al estar en {ciudad_detectada.title()}, podemos ayudarte. Ahora cuéntame: ¿Cuentas con cupo disponible en tu recibo del agua?"
            texto_final = _obtener_respuesta_comercial(texto_input, guion)
            return {"texto": texto_final, "botones": ["Soy Titular", "Familiar", "No cupo"]}

        db.guardar_progreso_cliente(wid, estado="FUERA_ZONA")
        guion = "Lo siento, por ahora solo operamos en Barranquilla y el departamento del Atlántico. Si quieres corregir tu ubicación, escribe 'reiniciar'. 📍"
        texto_final = _obtener_respuesta_comercial(texto_input, guion)
        return {"texto": texto_final}

    # --- ESTADO: TIPO_CUPO ---
    if estado_actual == "TIPO_CUPO":
        texto_lc = texto_input.lower()
        if "no" in texto_lc or "ningun" in texto_lc:
            tipo_cupo = "No cupo"
        elif "titular" in texto_lc:
            tipo_cupo = "Soy Titular"
        elif "familiar" in texto_lc:
            tipo_cupo = "Familiar"
        else:
            tipo_cupo = texto_input

        if tipo_cupo == "No cupo":
            db.guardar_progreso_cliente(wid, tipo_cupo="No cupo", estado="NO_CUPO")
            guion = "Entiendo, amigo. También manejamos excelentes opciones con entidades financieras aliadas. Pero antes de seguir, cuéntame: ¿Te encuentras reportado en centrales de riesgo o Datacrédito?"
            texto_final = _obtener_respuesta_comercial(texto_input, guion)
            return {"texto": texto_final, "botones": ["Sí, estoy reportado", "No, estoy limpio"]}

        db.guardar_progreso_cliente(wid, tipo_cupo=tipo_cupo, estado="TRANSP")
        guion = "¡Excelente! Para brindarte la mejor asesoría, cuéntame un poco sobre tu rutina: ¿Cuánto te estás gastando aproximadamente al día en transporte (buses, moto-taxis, etc.)?"
        texto_final = _obtener_respuesta_comercial(texto_input, guion)
        return {"texto": texto_final, "botones": ["10k-15k", "15k-20k", "+20k"]}

    # --- ESTADO: TRANSP ---
    if estado_actual == "TRANSP":
        rango = await _clasificar_transporte_con_ollama(texto_input)
        if rango:
            db.guardar_progreso_cliente(wid, gasto_transporte=rango, estado="BRILLA_DILO", necesita_agente=1)
            guion = "¡Wow! Estás gastando bastante dinero en transporte público. Con ese mismo dinero diario podrías estar pagando la cuota de tu propia moto nueva y dejar de regalar la plata. Ya mismo le pasé tus datos a uno de nuestros asesores comerciales para que te contacte y te ayude con el proceso. ¡Pronto te hablaremos! 🏍️"
            texto_final = _obtener_respuesta_comercial(texto_input, guion)
            return {"texto": texto_final, "necesita_agente": True}
            
        guion = "Por favor, cuéntame cuánto gastas diariamente en transporte para poder hacerte el cálculo. Ejemplo: entre 10 y 15 mil, o más de 20 mil."
        texto_final = _obtener_respuesta_comercial(texto_input, guion)
        return {"texto": texto_final, "botones": ["10k-15k", "15k-20k", "+20k"]}

    # --- ESTADO: NO_CUPO ---
    if estado_actual == "NO_CUPO":
        esta_reportado = await _detectar_afirmacion_con_ollama(texto_input)
        if esta_reportado:
            db.guardar_progreso_cliente(wid, reportado=1, estado="RECHAZADO")
            guion = "Entiendo, amigo. Lamentablemente en este momento no podemos procesar solicitudes de crédito financiero si cuentas con reportes activos en centrales de riesgo. Te invitamos a regularizar tu situación y volver a consultarnos en el futuro. ¡Muchas gracias por tu interés!"
            texto_final = _obtener_respuesta_comercial(texto_input, guion)
            return {"texto": texto_final}

        db.guardar_progreso_cliente(wid, reportado=0, estado="BANCA")
        guion = "¡Buenísimo que estés limpio! Podemos explorar el crédito por medio de nuestros aliados financieros bancarios. Cuéntame, ¿qué tan pronto te gustaría tener rodando tu moto nueva?"
        texto_final = _obtener_respuesta_comercial(texto_input, guion)
        return {"texto": texto_final, "botones": ["Hoy mismo", "Esta semana", "El próximo mes"]}

    # --- ESTADO: BANCA ---
    if estado_actual == "BANCA":
        db.guardar_progreso_cliente(wid, tiempo_entrega=texto_input, estado="TIEMPO_ENTREGA", necesita_agente=1)
        guion = "¡Perfecto! Ya registré tu interés. Uno de nuestros asesores comerciales especializados se comunicará contigo vía telefónica para validar tus opciones de crédito, estudiar el perfil y concretar la entrega de tu moto. ¡Muchas gracias por confiar en nosotros! 🚀"
        texto_final = _obtener_respuesta_comercial(texto_input, guion)
        return {"texto": texto_final, "necesita_agente": True}

    # --- ESTADO: FUERA_ZONA ---
    if estado_actual == "FUERA_ZONA":
        ciudad_detectada = await _extraer_ciudad_con_ollama(texto_input)
        if ciudad_detectada:
            db.guardar_progreso_cliente(wid, ciudad=ciudad_detectada, estado="TIPO_CUPO")
            guion = f"¡Perfecto! Al estar en {ciudad_detectada.title()}, podemos ayudarte. Ahora cuéntame: ¿Cuentas con cupo disponible en tu recibo del agua?"
            texto_final = _obtener_respuesta_comercial(texto_input, guion)
            return {"texto": texto_final, "botones": ["Soy Titular", "Familiar", "No cupo"]}
        return {"texto": "Por ahora, nuestro sistema solo opera para Barranquilla y municipios del departamento del Atlántico. Si deseas corregir tu ubicación, escribe 'reiniciar'. 📍"}

    # --- ESTADO: RECORDATORIO_ENVIADO (Si responde tras el aviso de inactividad) ---
    if estado_actual == "RECORDATORIO_ENVIADO":
        db.guardar_progreso_cliente(wid, estado="INICIO", ultima_interaccion=ahora_str)
        return {"texto": "¡Hola de nuevo! Retomemos el proceso desde el principio para asegurar tus datos. ¿En qué ciudad te encuentras actualmente? 🏍️"}

    # --- ESTADOS FINALES ---
    if estado_actual in estados_finales:
        return {"texto": "Tu solicitud ya se encuentra registrada y en proceso con nuestro equipo comercial. Muy pronto te estaremos contactando. ¡Ten un excelente día! 📞", "necesita_agente": True}

    return {"texto": "Lo siento, ocurrió un inconveniente al procesar tu mensaje. Por favor, escribe 'reiniciar' para volver a intentarlo."}


# =====================================================================
# MOTOR PROACTIVO (BUCLE ASÍNCRONO EN SEGUNDO PLANO)
# =====================================================================
async def verificar_inactividad_proactiva_loop(enviar_mensaje_whatsapp_callback):
    """
    Bucle infinito diseñado para ejecutarse como Background Task en FastAPI (main.py).
    Se despierta cada 5 minutos, escanea la base de datos y toma acciones proactivas.
    
    Requiere pasarle como parámetro la función/callback asíncrona que usas para disparar 
    los mensajes de salida hacia la API Cloud de Meta.
    """
    db = MotosDAO()
    print("🚀 Motor de Inactividad Proactiva inicializado con éxito.")
    
    while True:
        await asyncio.sleep(300)  # Latencia de escaneo: Cada 5 minutos (300 segundos)
        ahora = datetime.now()
        
        # Trae todos los leads abiertos (clientes que NO estén en estados finales)
        clientes_activos = db.obtener_clientes_en_proceso() 
        
        for cliente in clientes_activos:
            wid = cliente['wid']
            estado = cliente['estado']
            
            if not cliente.get('ultima_interaccion'):
                continue
                
            try:
                ultima_vez = datetime.strptime(cliente['ultima_interaccion'], "%Y-%m-%d %H:%M:%S")
                tiempo_silencio = ahora - ultima_vez
                
                # REGLA 1: Lleva más de 15 minutos en silencio y está en un estado intermedio regular
                if tiempo_silencio > timedelta(minutes=15) and estado != "RECORDATORIO_ENVIADO":
                    db.guardar_progreso_cliente(wid, estado="RECORDATORIO_ENVIADO", ultima_interaccion=ahora.strftime("%Y-%m-%d %H:%M:%S"))
                    
                    msg = "¿Sigues ahí? Cuéntame para poder continuar con la asesoría de tu moto. ⏱️"
                    await enviar_mensaje_whatsapp_callback(wid, msg)
                    print(f"⏱️ [PROACTIVO] Primer aviso enviado a {wid} (Inactivo por {tiempo_silencio.seconds // 60} min)")

                # REGLA 2: Ya se le envió el recordatorio, pasaron otros 15 minutos de silencio (30 en total) y no contestó
                elif tiempo_silencio > timedelta(minutes=15) and estado == "RECORDATORIO_ENVIADO":
                    db.cerrar_y_crear_nueva_sesion(wid)
                    db.guardar_progreso_cliente(wid, estado="INICIO", ultima_interaccion=ahora.strftime("%Y-%m-%d %H:%M:%S"))
                    
                    msg = "Veo que estás ocupado. Aquí estaré cuando decidas volver. ¡Feliz día! 🏍️"
                    await enviar_mensaje_whatsapp_callback(wid, msg)
                    print(f"⏱️ [PROACTIVO] Sesión cerrada definitivamente por abandono para {wid}")
                    
            except Exception as e:
                print(f"❌ Error procesando inactividad proactiva para {wid}: {e}")