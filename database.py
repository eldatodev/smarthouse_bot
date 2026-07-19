# database.py
import sqlite3
import os
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env
load_dotenv()
DB_NAME = os.getenv("DB_NAME", "motos_chatbot.db")

class MotosDAO:
    def __init__(self):
        self._crear_tabla()

    def _conectar(self):
        return sqlite3.connect(DB_NAME)

    def _crear_tabla(self):
        with self._conectar() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wid TEXT NOT NULL,
                    nombre TEXT,
                    estado TEXT NOT NULL DEFAULT 'INICIO',
                    estado_anterior TEXT,
                    ciudad TEXT,
                    tipo_cupo TEXT,
                    gasto_transporte TEXT,
                    reportado INTEGER DEFAULT 0,
                    tiempo_entrega TEXT,
                    necesita_agente INTEGER DEFAULT 0,
                    ultima_interaccion TEXT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    activa INTEGER DEFAULT 1
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_wid ON clientes (wid)")
            conn.commit()

    def obtener_cliente(self, wid: str) -> Optional[Dict[str, Any]]:
        """Trae únicamente la sesión comercial activa (1) o evalúa si está en atención manual (bloqueo del bot)."""
        with self._conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Buscamos la última sesión registrada en general para el usuario
            cursor.execute(
                "SELECT * FROM clientes WHERE wid = ? ORDER BY id DESC LIMIT 1", 
                (wid,)
            )
            row = cursor.fetchone()
            if row:
                cliente = dict(row)
                cliente['reportado'] = bool(cliente['reportado']) if cliente['reportado'] is not None else None
                cliente['necesita_agente'] = bool(cliente['necesita_agente'])
                
                # Si la sesión no está activa pero requiere agente, validamos si fue en las últimas 24 horas
                if not cliente['activa'] and cliente['necesita_agente']:
                    if cliente.get('ultima_interaccion'):
                        try:
                            ultima_vez = datetime.strptime(cliente['ultima_interaccion'], "%Y-%m-%d %H:%M:%S")
                            if datetime.now() - ultima_vez < timedelta(hours=24):
                                # Retorna el cliente en un estado virtual para silenciar al bot
                                cliente['estado'] = "ATENCION_MANUAL"
                                return cliente
                        except ValueError:
                            pass
                
                # Si la sesión está activa (1), la retorna normalmente
                if cliente['activa']:
                    return cliente
            return None

    def obtener_clientes_en_proceso(self) -> list[Dict[str, Any]]:
        """
        Trae todos los leads con sesión activa (1) que NO han llegado a un estado final.
        Esencial para que el bucle asíncrono proactivo evalúe los tiempos de inactividad.
        """
        with self._conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Filtramos para ignorar hilos cerrados, rechazados o que ya están con agente
            cursor.execute("""
                SELECT * FROM clientes 
                WHERE activa = 1 
                  AND estado NOT IN ('RECHAZADO', 'TIEMPO_ENTREGA', 'BRILLA_DILO')
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def guardar_progreso_cliente(self, wid: str, **kwargs) -> None:
        """Actualiza la sesión activa del usuario o crea una nueva si no existe."""
        cliente_actual = self.obtener_cliente(wid)
        
        with self._conectar() as conn:
            cursor = conn.cursor()
            if not cliente_actual:
                # Si no hay sesión activa abierta para este número, creamos una fila nueva
                columnas = ["wid", "estado", "activa"] + list(kwargs.keys())
                valores = [wid, "INICIO", 1] + list(kwargs.values())
                placeholders = ", ".join(["?"] * len(valores))
                
                query = f"INSERT INTO clientes ({', '.join(columnas)}) VALUES ({placeholders})"
                cursor.execute(query, valores)
            else:
                # Si hay una sesión activa, modificamos solo esa fila mediante su ID único
                id_fila = cliente_actual['id']
                if kwargs:
                    columnas_update = ", ".join([f"{k} = ?" for k in kwargs.keys()])
                    valores = list(kwargs.values()) + [id_fila]
                    query = f"UPDATE clientes SET {columnas_update} WHERE id = ?"
                    cursor.execute(query, valores)
            conn.commit()
            print(f"   [DB SQLITE] Progreso guardado para {wid} -> {kwargs}")

    def cerrar_y_crear_nueva_sesion(self, wid: str) -> None:
        """Archiva la sesión actual pasándola a inactiva (0) para proteger el historial."""
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE clientes SET activa = 0 WHERE wid = ? AND activa = 1", (wid,))
            conn.commit()
            print(f"   [DB SQLITE] Sesión de {wid} archivada en el historial. Listo para una conversación nueva.")