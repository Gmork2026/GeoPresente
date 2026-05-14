from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# ⚠️ IMPORTANTE: Pega aquí la URL que obtuviste al implementar Google Apps Script
GAS_URL = "URL_DE_TU_APPS_SCRIPT_AQUI"

# --- 1. MODELOS DE DATOS (Entrada esperada del Frontend) ---
class MarcacionIn(BaseModel):
    legajo: int
    tipo_marcacion: str  # "INGRESO" o "SALIDA"
    latitud_celular: float
    longitud_celular: float
    selfie_b64: str

# --- 2. LÓGICA MATEMÁTICA (Fórmula de Haversine) ---
def calcular_distancia(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia exacta en metros entre dos coordenadas GPS."""
    R = 6371000  # Radio de la Tierra en metros
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi_1) * math.cos(phi_2) * \
        math.sin(delta_lambda / 2.0) ** 2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- 3. CONEXIÓN A LA BASE DE DATOS (Google Sheets) ---
def obtener_servicios():
    """Llama a tu Google Apps Script para traer la lista de servicios actualizada."""
    try:
        response = requests.get(f"{GAS_URL}?action=servicios")
        data = response.json()
        if data.get("status") == "success":
            return data.get("data", [])
        return []
    except Exception as e:
        print(f"Error conectando a Sheets: {e}")
        return []

# --- 4. ENDPOINT PRINCIPAL ---
@app.get("/")
def read_root():
    return {"status": "online", "sistema": "GeoPresente API", "version": "1.0"}

@app.post("/api/marcar")
def procesar_marcacion(datos: MarcacionIn):
    servicios = obtener_servicios()
    if not servicios:
        raise HTTPException(status_code=500, detail="No se pudieron cargar los servicios desde la base de datos.")

    servicio_cercano = None
    distancia_minima = float('inf')

    # Buscar el servicio más cercano matemáticamente
    for servicio in servicios:
        try:
            # Adaptamos las claves según los encabezados que definimos en tu hoja
            lat_serv = float(servicio["Latitud"])
            lon_serv = float(servicio["Longitud"])
            tolerancia = int(servicio["Tolerancia_Metros"])
        except (ValueError, KeyError):
            continue # Si una fila tiene datos vacíos o erróneos, la ignoramos para que no caiga el servidor

        dist = calcular_distancia(datos.latitud_celular, datos.longitud_celular, lat_serv, lon_serv)
        
        if dist < distancia_minima:
            distancia_minima = dist
            servicio_cercano = servicio
            servicio_cercano["tolerancia_activa"] = tolerancia

    if not servicio_cercano:
        raise HTTPException(status_code=400, detail="No se detectó ningún servicio.")

    # Validar si está dentro de la tolerancia permitida
    es_valida = False
    observaciones = "Ok"
    
    if distancia_minima <= servicio_cercano["tolerancia_activa"]:
        es_valida = True
    else:
        es_valida = False
        observaciones = f"Fuera de rango por {int(distancia_minima - servicio_cercano['tolerancia_activa'])} metros."

    # Estructuramos la respuesta final
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
        "selfie_url": "PENDIENTE_N8N" # n8n procesará la foto luego
    }

    return {"status": "success", "data": resultado}