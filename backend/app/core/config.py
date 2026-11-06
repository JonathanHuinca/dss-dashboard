from typing import List, Optional
import os
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


VALORES_INSEGUROS_EJEMPLO = {
    "cambia-esto",
    "tu-secreto",
    "password",
    "secret",
    "123456",
    "default",
    "ejemplo",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Entorno y Zona Horaria
    ENVIRONMENT: str = "development"
    TZ: str = "America/Santiago"

    # Credenciales de Base de Datos SQL Server
    MSSQL_SA_PASSWORD: str = ""
    MSSQL_USUARIO_APP: str = "uct_app"
    MSSQL_CLAVE_APP: str = ""

    # Cadenas de conexión (por defecto vacías o estructuradas para uct_app sobre uct_dashboard)
    DATABASE_URL: str = "mssql+aioodbc://uct_app:clave_local@db:1433/uct_dashboard?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    DATABASE_URL_SYNC: str = "mssql+pyodbc://uct_app:clave_local@db:1433/uct_dashboard?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

    # Seguridad y Criptografía (Ley N° 21.719)
    JWT_SECRET_KEY: str = "clave-secreta-desarrollo-minimo-32-caracteres-uct"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SALT_PERSON_SECRET: str = "salt-desarrollo-sha256-persona-uct-csf"
    SALT_VEHICLE_SECRET: str = "salt-desarrollo-sha256-vehiculo-uct-csf"
    FERNET_KEY: str = ""

    # Inteligencia Artificial y LLM
    GEMINI_API_KEY: str = ""
    PANDASAI_LLM_API_KEY: str = ""
    TIEMPO_ESPERA_LLM_SEGUNDOS: int = 20
    MODELO_GEMINI_POR_DEFECTO: str = "gemini-3.5-flash-lite"

    # Planificador Interno (APScheduler)
    PLANIFICADOR_ACTIVO: bool = True
    TIEMPO_MAXIMO_TAREA_MINUTOS: int = 30

    # Modelos de Machine Learning
    DIRECTORIO_MODELOS: str = "models"
    HORA_ENTRENAMIENTO_DIARIO: str = "06:00"

    # Retención de datos y purga de chat (días)
    RETENCION_CHAT_DIAS: int = 30

    # Control de Semilla y Usuarios Demo
    SEMILLA_DEMO: bool = True
    DEMO_ADMIN_PASSWORD: str = "AdminUCT2026!"
    DEMO_USER_PASSWORD: str = "UCTdemo2026!"

    # Seguridad de Red y Control Perimetral
    ENABLE_IP_WHITELIST: bool = False
    ALLOWED_SUBNETS: str = "10.20.0.0/16,127.0.0.1/32"
    FRONTEND_URL: str = "http://localhost:3000"

    # Servidor de Correo SMTP institucional
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@uct.cl"
    SMTP_FROM_NAME: str = "DSS Campus San Francisco - UCT"
    SMTP_USE_TLS: bool = True

    # Integración ANPR HikCentral
    HIKCENTRAL_BASE_URL: str = "https://hikcentral.uct.cl"
    HIKCENTRAL_APP_KEY: str = ""
    HIKCENTRAL_APP_SECRET: str = ""
    HIKCENTRAL_CA_BUNDLE: Optional[str] = None
    HIKCENTRAL_ESPACIOS: str = '{"1": "REGION_BIBLIOTECA", "2": "REGION_ESTACIONAMIENTO"}'

    # Ingesta Masiva y Almacenamiento de Archivos (volumen ingesta_archivos)
    DIRECTORIO_INGESTA: str = "datos_ingesta"
    TAMANO_MAXIMO_INGESTA_MB: int = 100
    EXTENSIONES_INGESTA_PERMITIDAS: str = ".csv,.xlsx,.xls"

    # Integración Directa API Smart Campus UCT
    SMART_CAMPUS_API_URL: str = "https://integrasmartcampus.uct.cl/api/lectura"
    LECTURA_API_KEY: Optional[str] = None

    # Modelos Predictivos y Calendario Académico
    MINIMO_EVENTOS_CALENDARIO: int = 20

    @property

    def allowed_subnets_list(self) -> List[str]:
        return [s.strip() for s in self.ALLOWED_SUBNETS.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @model_validator(mode="after")
    def validar_secretos_produccion(self) -> "Settings":
        """
        Verifica secretos en producción y genera valores seguros de respaldo en memoria
        si algún secreto opcional no fue definido en el servidor, evitando caídas de arranque (502).
        """
        import logging
        _log = logging.getLogger("uvicorn.error")
        if not self.FERNET_KEY or not self.FERNET_KEY.strip():
            try:
                from cryptography.fernet import Fernet
                import base64, hashlib
                semilla = (self.JWT_SECRET_KEY or "uct-dss-fallback-key").encode("utf-8")
                self.FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(semilla).digest()).decode("utf-8")
            except Exception:
                pass
        if self.is_production:
            if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY.strip()) < 32:
                _log.warning("Aviso de seguridad: JWT_SECRET_KEY tiene menos de 32 caracteres en producción.")
            if not self.GEMINI_API_KEY or len(self.GEMINI_API_KEY.strip()) < 10:
                _log.warning("Aviso de configuración: GEMINI_API_KEY no definida en producción.")
        return self


settings = Settings()
