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
    MODELO_GEMINI_POR_DEFECTO: str = "gemini-3.5-flash"

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
    DEMO_ADMIN_PASSWORD: str = ""
    DEMO_USER_PASSWORD: str = ""

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
        Valida que en producción no se utilicen secretos vacíos o con valores de plantilla.
        Falla inmediatamente el arranque de la aplicación si se detecta inseguridad.
        """
        if self.is_production:
            # Validación JWT_SECRET_KEY
            if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY.strip()) < 32:
                raise ValueError("En producción, JWT_SECRET_KEY debe tener al menos 32 caracteres.")
            for patron in VALORES_INSEGUROS_EJEMPLO:
                if patron.lower() in self.JWT_SECRET_KEY.lower():
                    raise ValueError(f"En producción, JWT_SECRET_KEY no puede contener valores de ejemplo: '{patron}'")

            # Validación FERNET_KEY
            if not self.FERNET_KEY or not self.FERNET_KEY.strip():
                raise ValueError("En producción, FERNET_KEY es obligatoria y no puede estar vacía.")
            for patron in VALORES_INSEGUROS_EJEMPLO:
                if patron.lower() in self.FERNET_KEY.lower():
                    raise ValueError(f"En producción, FERNET_KEY no puede usar claves de ejemplo: '{patron}'")
            try:
                from cryptography.fernet import Fernet
                Fernet(self.FERNET_KEY.strip().encode())
            except Exception as e:
                raise ValueError(f"En producción, FERNET_KEY debe ser una clave Fernet válida en base64 de 32 bytes: {e}")

            # Validación SALT_PERSON_SECRET y SALT_VEHICLE_SECRET
            if not self.SALT_PERSON_SECRET or len(self.SALT_PERSON_SECRET.strip()) < 16:
                raise ValueError("En producción, SALT_PERSON_SECRET debe tener al menos 16 caracteres.")
            if not self.SALT_VEHICLE_SECRET or len(self.SALT_VEHICLE_SECRET.strip()) < 16:
                raise ValueError("En producción, SALT_VEHICLE_SECRET debe tener al menos 16 caracteres.")
            for patron in VALORES_INSEGUROS_EJEMPLO:
                if patron.lower() in self.SALT_PERSON_SECRET.lower():
                    raise ValueError(f"En producción, SALT_PERSON_SECRET no puede usar valores de ejemplo: '{patron}'")
                if patron.lower() in self.SALT_VEHICLE_SECRET.lower():
                    raise ValueError(f"En producción, SALT_VEHICLE_SECRET no puede usar valores de ejemplo: '{patron}'")

            # Validación GEMINI_API_KEY
            if not self.GEMINI_API_KEY or len(self.GEMINI_API_KEY.strip()) < 10:
                raise ValueError("En producción, GEMINI_API_KEY es obligatoria para el funcionamiento del DSS.")

        return self


settings = Settings()
