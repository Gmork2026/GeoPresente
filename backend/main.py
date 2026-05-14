from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="GeoPresente API")

# Configuración de CORS (Crucial para que Vercel pueda hablar con Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En producción cambiaremos "*" por tu URL de Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "online", "sistema": "GeoPresente API", "version": "1.0"}

@app.get("/health")
def health_check():
    return {"status": "ok"}