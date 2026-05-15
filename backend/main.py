from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import math
import requests

app = FastAPI(title="GeoPresente API", version="1.0")

# --- CONFIGURACIÓN CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ⚠️ IMPORTANTE: Pega aquí la URL de tu Apps Script
GAS_URL = "https://script.google.com/macros/s/AKfycbzsj8bjSlAyubBGQm7KORL4tV-k5bp1hBxlLcfyVoTs2QMyCLJ6RdNmw_OGwfOD19V3/exec"

# --- 1. MODELOS DE DATOS ---
class MarcacionIn(BaseModel):
    legajo: int
    nombre_nuevo: Optional[str] = None
    dni_nuevo: Optional[str] = None
    tipo_marcacion: str  
    latitud_celular: float
    longitud_celular: float
    selfie_b64: str

# --- 2. LÓGICA MATEMÁTICA (Haversine) ---
def calcular_distancia(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000  
    phi_1, phi_2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- 3. CONEXIÓN A LA BASE DE DATOS (Google Sheets) ---
def obtener_servicios():
    try:
        res = requests.get(f"{GAS_URL}?action=servicios")
        return res.json().get("data", []) if res.json().get("status") == "success" else []
    except: return []

def obtener_vigiladores():
    """Llama a Google Apps Script para traer la lista de vigiladores."""
    try:
        res = requests.get(f"{GAS_URL}?action=vigiladores")
        return res.json().get("data", []) if res.json().get("status") == "success" else []
    except Exception as e:
        print(f"Error conectando a Sheets (Vigiladores): {e}")
        return []

# --- 4. ENDPOINTS ---
@app.get("/")
def read_root():
    return {"status": "online", "sistema": "GeoPresente API"}

# NUEVO ENDPOINT: Validar Legajo
@app.get("/api/validar/{legajo}")
def validar_legajo(legajo: int):
    vigiladores = obtener_vigiladores()
    
    # Buscamos si el legajo está en la lista (convertimos a str para asegurar la coincidencia)
    for v in vigiladores:
        if str(v.get("Legajo")) == str(legajo):
            return {
                "status": "success", 
                "existe": True, 
                "nombre": v.get("Nombre_Completo", "Vigilador")
            }
            
    # Si termina el bucle y no lo encontró
    return {"status": "success", "existe": False}


@app.post("/api/marcar")
def procesar_marcacion(datos: MarcacionIn):
    servicios = obtener_servicios()
    if not servicios:
        raise HTTPException(status_code=500, detail="Error de DB")

    servicio_cercano = None
    distancia_minima = float('inf')

    for servicio in servicios:
        try:
            lat_serv = float(servicio["Latitud"])
            lon_serv = float(servicio["Longitud"])
            # Ajustamos el código al nombre exacto de tu columna
            tolerancia = int(servicio["Tolerancia en metro"]) 
        except (ValueError, KeyError) as e:
            print(f"Error procesando fila: {e}") # Esto nos ayudará a ver en Render si hay filas vacías
            continue

        dist = calcular_distancia(datos.latitud_celular, datos.longitud_celular, lat_serv, lon_serv)
        
        if dist < distancia_minima:
            distancia_minima = dist
            servicio_cercano = servicio
            servicio_cercano["tolerancia_activa"] = tolerancia

    if not servicio_cercano:
        raise HTTPException(status_code=400, detail="No se detectó ningún servicio.")

    es_valida = distancia_minima <= servicio_cercano["tolerancia_activa"]
    
    # Manejo de Observaciones
    observaciones = "Ok"
    if datos.nombre_nuevo:
        # Si es nuevo, guardamos su nombre y su DNI en las observaciones
        observaciones = f"NUEVO USUARIO: {datos.nombre_nuevo} - DNI: {datos.dni_nuevo}."
        
    if not es_valida:
        desvio = int(distancia_minima - servicio_cercano['tolerancia_activa'])
        observaciones += f" Fuera de rango por {desvio}m."

    # Preparamos el paquete completo para n8n
    resultado = {
        "legajo": datos.legajo,
        "tipo_marcacion": datos.tipo_marcacion,
        "id_servicio": servicio_cercano.get("ID", "N/A"),
        "descripcion_servicio": servicio_cercano.get("Descripcion", "Desconocido"),
        "lat_celular": datos.latitud_celular,
        "lon_celular": datos.longitud_celular,
        "distancia_metros": round(distancia_minima, 2),
        "es_valida": es_valida,
        "observaciones": observaciones,
        "selfie_b64": datos.selfie_b64, # ⚠️ CAMBIO VITAL: Enviamos la foto real a n8n
        "is_nuevo_usuario": True if datos.nombre_nuevo else False,
        "nombre_nuevo": datos.nombre_nuevo,
        "dni_nuevo": datos.dni_nuevo
    }

    # ⚠️ PEGA AQUÍ LA TEST URL DE TU NODO WEBHOOK DE n8n
    N8N_WEBHOOK_URL = "https://n8n-production-115e.up.railway.app/webhook-test/marcar-presentismo"

    try:
        # Enviamos el paquete a n8n en lugar de ir directo a Google Sheets
        requests.post(N8N_WEBHOOK_URL, json=resultado)
    except Exception as e:
        print(f"Error enviando a n8n: {e}")

    return {"status": "success", "data": resultado}