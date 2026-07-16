# test_bot.py
import asyncio
import os
import sys

# Mockear el envío de mensajes a WhatsApp para evitar llamadas reales de red en el test
import main
mensajes_enviados = []
async def mock_enviar_mensaje(to_wid, texto_bot):
    print(f"   [Mock WhatsApp] Enviando a {to_wid}: \n---\n{texto_bot}\n---")
    mensajes_enviados.append((to_wid, texto_bot))

main.enviar_mensaje_whatsapp_real = mock_enviar_mensaje

from database import MotosDAO
from chatbot_logic import procesar_mensaje, _normalizar_texto
from main import manejar_flujo_async

async def run_tests():
    print("--- Limpiando base de datos de prueba ---")
    db_file = "motos_chatbot.db"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            print("Base de datos anterior eliminada físicamente.")
        except Exception as e:
            print(f"No se pudo eliminar la base de datos activa (bloqueada por otro proceso): {e}")
            print("Se procederá a archivar sesiones de prueba anteriores en la base de datos existente.")

    db = MotosDAO()
    
    # Definición de números de prueba
    WID = "573001234567@c.us"
    WID_FAMILIAR = "573007654321@c.us"
    WID_REPORTADO = "573001111111@c.us"
    WID_INACTIVO = "573002222222@c.us"
    WID_ASESOR_TEST = "573008888888@c.us"
    NOMBRE = "Maria"

    # Archivar cualquier sesión activa previa para estos números de prueba
    db.cerrar_y_crear_nueva_sesion(WID)
    db.cerrar_y_crear_nueva_sesion(WID_FAMILIAR)
    db.cerrar_y_crear_nueva_sesion(WID_REPORTADO)
    db.cerrar_y_crear_nueva_sesion(WID_INACTIVO)
    db.cerrar_y_crear_nueva_sesion(WID_ASESOR_TEST)

    print("\n--- PRUEBA 1: Flujo Exitoso con Cupo Brilla y Gasto de Transporte ---")
    # Saludo inicial
    r = await procesar_mensaje(WID, "", NOMBRE)
    print(f"Bot (Inicio): {r['texto']}")
    assert "ciudad" in r['texto'].lower()

    # Enviar ciudad
    r = await procesar_mensaje(WID, "Estoy en Barranquilla", NOMBRE)
    print(f"Bot (Ciudad): {r['texto']}")
    assert "recibo del agua" in r['texto'].lower()

    # Enviar Tipo Cupo (Titular)
    r = await procesar_mensaje(WID, "Soy titular del recibo", NOMBRE)
    print(f"Bot (Cupo): {r['texto']}")
    assert "transporte" in r['texto'].lower()

    # Enviar Gasto de Transporte
    r = await procesar_mensaje(WID, "Gasto como 15 mil pesos al dia", NOMBRE)
    print(f"Bot (Gasto): {r['texto']}")
    assert "asesores" in r['texto'].lower()
    
    # Verificar base de datos
    cli = db.obtener_cliente(WID)
    print(f"Cliente en BD: Estado={cli['estado']}, Ciudad={cli['ciudad']}, Gasto={cli['gasto_transporte']}, Agente={cli['necesita_agente']}")
    assert cli['estado'] == "BRILLA_DILO"
    assert cli['necesita_agente'] == True

    print("\n--- PRUEBA 2: Validacion de Prioridad Familiar vs 'No' ---")
    # Saludo
    await procesar_mensaje(WID_FAMILIAR, "", NOMBRE)
    # Ciudad
    await procesar_mensaje(WID_FAMILIAR, "Soledad", NOMBRE)
    # Tipo Cupo: "No soy el titular, es de un familiar"
    r = await procesar_mensaje(WID_FAMILIAR, "No soy el titular, es de un familiar", NOMBRE)
    print(f"Bot (Cupo familiar): {r['texto']}")
    
    # Debe haber avanzado a TRANSP y no haber ido a NO_CUPO
    cli_fam = db.obtener_cliente(WID_FAMILIAR)
    print(f"Cliente Familiar en BD: Estado={cli_fam['estado']}, Tipo Cupo={cli_fam['tipo_cupo']}")
    assert cli_fam['estado'] == "TRANSP"
    assert cli_fam['tipo_cupo'] == "Familiar"

    print("\n--- PRUEBA 3: Flujo Bancario (Sin Cupo) and Deteccion de Reportado ---")
    await procesar_mensaje(WID_REPORTADO, "", NOMBRE)
    await procesar_mensaje(WID_REPORTADO, "soledad", NOMBRE)
    # Tipo Cupo: No tengo cupo
    r = await procesar_mensaje(WID_REPORTADO, "no tengo cupo de agua", NOMBRE)
    print(f"Bot (Sin cupo): {r['texto']}")
    assert "reportado" in r['texto'].lower()

    # Responder que si esta reportado
    r = await procesar_mensaje(WID_REPORTADO, "Si, lastimosamente tengo un reporte en datacredito", NOMBRE)
    print(f"Bot (Reportado): {r['texto']}")
    assert "lamentablemente" in r['texto'].lower()
    
    cli_rep = db.obtener_cliente(WID_REPORTADO)
    print(f"Cliente Reportado en BD: Estado={cli_rep['estado']}, Reportado={cli_rep['reportado']}")
    assert cli_rep['estado'] == "RECHAZADO"
    assert cli_rep['reportado'] == True

    print("\n--- PRUEBA 4: Recuperacion de Estado tras Inactividad ---")
    await procesar_mensaje(WID_INACTIVO, "", NOMBRE)
    await procesar_mensaje(WID_INACTIVO, "Barranquilla", NOMBRE)
    
    # El usuario quedo en el estado TIPO_CUPO.
    cli_inac = db.obtener_cliente(WID_INACTIVO)
    print(f"Estado antes de inactividad: {cli_inac['estado']}")
    assert cli_inac['estado'] == "TIPO_CUPO"

    # Simulamos que la tarea proactiva le envia un recordatorio
    db.guardar_progreso_cliente(WID_INACTIVO, estado="RECORDATORIO_ENVIADO", estado_anterior=cli_inac['estado'])
    
    cli_inac_recordatorio = db.obtener_cliente(WID_INACTIVO)
    print(f"Estado con recordatorio enviado: {cli_inac_recordatorio['estado']}, Estado anterior guardado: {cli_inac_recordatorio['estado_anterior']}")
    assert cli_inac_recordatorio['estado'] == "RECORDATORIO_ENVIADO"
    assert cli_inac_recordatorio['estado_anterior'] == "TIPO_CUPO"

    # El usuario responde al recordatorio con su respuesta del cupo ("Soy el titular")
    r = await procesar_mensaje(WID_INACTIVO, "Soy el titular", NOMBRE)
    print(f"Bot (Al responder recordatorio): {r['texto']}")
    
    # Debe haber avanzado a TRANSP porque restauro el estado a TIPO_CUPO y proceso "Soy el titular"
    cli_restaurado = db.obtener_cliente(WID_INACTIVO)
    print(f"Cliente restaurado en BD: Estado actual={cli_restaurado['estado']}, Tipo Cupo={cli_restaurado['tipo_cupo']}")
    assert cli_restaurado['estado'] == "TRANSP"
    assert cli_restaurado['tipo_cupo'] == "Soy Titular"

    print("\n--- PRUEBA 5: Integracion de Notificacion al Asesor Comercial ---")
    os.environ["ASESOR_NUMBER"] = "573009999999"
    mensajes_enviados.clear()
    
    # Simular conversación completa usando manejar_flujo_async
    await manejar_flujo_async(WID_ASESOR_TEST, "", "Juan")
    await manejar_flujo_async(WID_ASESOR_TEST, "Barranquilla", "Juan")
    await manejar_flujo_async(WID_ASESOR_TEST, "Soy el titular del recibo", "Juan")
    await manejar_flujo_async(WID_ASESOR_TEST, "20000", "Juan") # Debe disparar agente
    
    print(f"Total mensajes mock enviados: {len(mensajes_enviados)}")
    assert len(mensajes_enviados) >= 2
    
    # Validar que el último mensaje es al asesor
    destinatario, texto = mensajes_enviados[-1]
    print(f"Destinatario de notificacion: {destinatario}")
    assert destinatario == "573009999999@c.us"
    assert "NUEVO LEAD CALIFICADO" in texto
    assert "Juan" in texto
    assert "20k" in texto

    print("\n--- TODAS LAS PRUEBAS SE COMPLETARON CON EXITO ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
