# chatbot_logic.py
import re
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
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

TIMEOUT_INACTIVIDAD = timedelta(hours=2)  # Tiempo límite pasivo para reiniciar hilos muertos

# =====================================================================
# FUNCIONES AUXILIARES DE NORMALIZACIÓN Y PROCESAMIENTO DETERMINISTA
# =====================================================================
def _normalizar_texto(texto: str) -> str:
    """Normaliza el texto de entrada quitando acentos, caracteres especiales y dobles espacios."""
    if not texto:
        return ""
    texto = texto.lower()
    # Reemplazar vocales acentuadas
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ü": "u", "ñ": "ñ"
    }
    for orig, dest in reemplazos.items():
        texto = texto.replace(orig, dest)
    # Conservar letras, números y espacios
    texto = re.sub(r'[^a-z0-9ñ\s]', '', texto)
    return " ".join(texto.split())


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
# EXTRACCIÓN INTELIGENTE DE DATOS CON FILTROS EN PYTHON (SIN OLLAMA)
# =====================================================================

async def _extraer_ciudad(texto_usuario: str) -> Optional[str]:
    """Extrae de manera determinista la ciudad/municipio de la lista de cobertura."""
    texto_lc = _normalizar_texto(texto_usuario)
    if not texto_lc or not texto_lc.strip():
        return None

    # Intentar coincidencia exacta en la lista de ciudades válidas
    palabras = texto_lc.split()
    for ciudad in CIUDADES_VALIDAS:
        # Si la ciudad consta de múltiples palabras (ej. "puerto colombia", "campo de la cruz")
        if ciudad in texto_lc:
            print(f"   [Filtro Python] Coincidencia por subcadena: '{ciudad}'")
            return ciudad
        # Si coincide con alguna palabra individual
        for palabra in palabras:
            if palabra == ciudad:
                print(f"   [Filtro Python] Coincidencia por palabra exacta: '{ciudad}'")
                return ciudad
    return None


async def _clasificar_transporte(texto_usuario: str) -> Optional[str]:
    """Clasifica el gasto diario en transporte en rangos fijos de forma determinista."""
    if not texto_usuario or not texto_usuario.strip():
        return None

    texto_lc = _normalizar_texto(texto_usuario)

    # 1. Coincidencia directa para clics en botones de WhatsApp
    if "10" in texto_lc and "15" in texto_lc:
        return "10k-15k"
    if "15" in texto_lc and "20" in texto_lc:
        return "15k-20k"
    if "20" in texto_lc:
        return "+20k"

    # 2. Reemplazo de sufijos comunes de miles
    texto_limpio = texto_lc.replace("mil", "000").replace("k", "000").replace(" ", "")
    numeros = re.findall(r'\d+', texto_limpio)
    
    if numeros:
        primer_numero = int(numeros[0])
        # Si ingresó el valor numérico completo (ej: 12000, 18000, 25000)
        if primer_numero >= 1000:
            if primer_numero >= 20000:
                print(f"   [Filtro Python] Número completo {primer_numero} -> '+20k'")
                return "+20k"
            elif 15000 <= primer_numero < 20000:
                print(f"   [Filtro Python] Número completo {primer_numero} -> '15k-20k'")
                return "15k-20k"
            elif 10000 <= primer_numero < 15000:
                print(f"   [Filtro Python] Número completo {primer_numero} -> '10k-15k'")
                return "10k-15k"
        else:
            # Si ingresó solo la cifra de miles (ej: 12, 15, 20)
            if primer_numero >= 20:
                print(f"   [Filtro Python] Cifra {primer_numero}k -> '+20k'")
                return "+20k"
            elif 15 <= primer_numero < 20:
                print(f"   [Filtro Python] Cifra {primer_numero}k -> '15k-20k'")
                return "15k-20k"
            elif 10 <= primer_numero < 15:
                print(f"   [Filtro Python] Cifra {primer_numero}k -> '10k-15k'")
                return "10k-15k"

    # 3. Expresiones textuales
    if "mas de veinte" in texto_lc or "mas de 20" in texto_lc or "bastante" in texto_lc:
        return "+20k"

    return None


async def _detectar_afirmacion(texto_usuario: str) -> bool:
    """Clasifica si el usuario afirma o niega un reporte crediticio de forma determinista."""
    if not texto_usuario or not texto_usuario.strip():
        return False

    texto_lc = _normalizar_texto(texto_usuario)
    
    negaciones = ["no", "ninguno", "falso", "limpio", "no estoy", "no tengo", "libre", "al dia", "sin reporte"]
    afirmaciones = ["si", "afirmativo", "correcto", "s", "claro", "reportado", "castigado", "datacredito", "tengo reporte"]

    palabras = texto_lc.split()
    
    # Validar si contiene alguna palabra clave de afirmación
    for af in afirmaciones:
        if af in texto_lc:
            # Comprobar que no esté negado justo antes
            for neg in negaciones:
                if f"{neg} {af}" in texto_lc or f"{neg} estoy {af}" in texto_lc or f"{neg} tengo {af}" in texto_lc:
                    print(f"   [Filtro Python] Afirmación '{af}' negada por '{neg}'")
                    return False
            print(f"   [Filtro Python] Afirmación detectada: '{af}'")
            return True

    # Comprobar respuestas cortas afirmativas de un solo carácter/palabra
    if "si" in palabras or "s" in palabras:
        print("   [Filtro Python] Respuesta corta afirmativa encontrada")
        return True

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

    # --- CONTROL DE ATENCIÓN MANUAL (HANDOVER) ---
    if estado_actual == "ATENCION_MANUAL":
        print(f"🤫 [SILENCIO] El cliente {wid} está siendo atendido por un agente. El bot no interrumpe.")
        return {}

    if any(keyword in texto_input.lower() for keyword in RESET_KEYWORDS):
        db.cerrar_y_crear_nueva_sesion(wid)
        db.guardar_progreso_cliente(wid, nombre=nombre_wa, estado="INICIO", ultima_interaccion=ahora_str)
        return {"texto": "Listo, empecemos de nuevo. ¿En qué ciudad te encuentras?"}

    # --- ESTADO: RECORDATORIO_ENVIADO (Si responde tras el aviso de inactividad) ---
    if estado_actual == "RECORDATORIO_ENVIADO":
        # Intentamos recuperar el estado anterior guardado
        estado_previo = cliente.get('estado_anterior') or "INICIO"
        
        # Restauramos el estado y procesamos el mensaje entrante en el contexto de ese estado previo
        db.guardar_progreso_cliente(wid, estado=estado_previo, estado_anterior=None, ultima_interaccion=ahora_str)
        # Volvemos a obtener el objeto de cliente actualizado
        cliente = db.obtener_cliente(wid)
        estado_actual = cliente['estado']
        print(f"⏱️ [PROACTIVO] Sesión de {wid} restaurada al estado previo: {estado_actual}")
        # NO hacemos return; dejamos que el flujo continúe evaluando el mensaje del usuario en el estado restaurado.

    # --- ESTADO: INICIO ---
    if estado_actual == "INICIO":
        if not texto_input:
            return {"texto": "¡Hola! Para empezar, cuéntame en qué ciudad te encuentras. 🏍️"}

        ciudad_detectada = await _extraer_ciudad(texto_input)
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
        texto_lc = _normalizar_texto(texto_input)
        
        # 1. Si menciona expresamente "familiar"
        if "familiar" in texto_lc:
            tipo_cupo = "Familiar"
        # 2. Si menciona "titular" pero niega la titularidad
        elif "titular" in texto_lc:
            # Validar si contiene la palabra "no" antes de la palabra "titular"
            if "no" in texto_lc.split() and texto_lc.find("no") < texto_lc.find("titular"):
                tipo_cupo = "No cupo"
            else:
                tipo_cupo = "Soy Titular"
        # 3. Si contiene "no" o "ningun"
        elif "no" in texto_lc.split() or "no cupo" in texto_lc or "ningun" in texto_lc:
            tipo_cupo = "No cupo"
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
        rango = await _clasificar_transporte(texto_input)
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
        esta_reportado = await _detectar_afirmacion(texto_input)
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
        ciudad_detectada = await _extraer_ciudad(texto_input)
        if ciudad_detectada:
            db.guardar_progreso_cliente(wid, ciudad=ciudad_detectada, estado="TIPO_CUPO")
            guion = f"¡Perfecto! Al estar en {ciudad_detectada.title()}, podemos ayudarte. Ahora cuéntame: ¿Cuentas con cupo disponible en tu recibo del agua?"
            texto_final = _obtener_respuesta_comercial(texto_input, guion)
            return {"texto": texto_final, "botones": ["Soy Titular", "Familiar", "No cupo"]}
        return {"texto": "Por ahora, nuestro sistema solo opera para Barranquilla y municipios del departamento del Atlántico. Si deseas corregir tu ubicación, escribe 'reiniciar'. 📍"}

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
                    db.guardar_progreso_cliente(
                        wid, 
                        estado="RECORDATORIO_ENVIADO", 
                        estado_anterior=estado, 
                        ultima_interaccion=ahora.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    
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