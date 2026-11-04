# Guía de Configuración de Desarrollo Local Híbrido (DSS UCT)

Este documento describe el flujo verificado para levantar la arquitectura del proyecto en un entorno local, combinando contenedores de Docker (Backend, SQL Server, Redis, Celery) con ejecución nativa (Vite/React).

## Requisitos Previos

- Docker y Docker Compose instalados.
- Node.js v18+ y npm instalados.
- Puerto `1433` (SQL Server), `6379` (Redis), `8000` (FastAPI), y `5173` (Vite) disponibles.

---

## 1. Archivos de Entorno y Configuración

### `docker-compose.local.yml`
En la raíz del proyecto, asegúrate de contar con el siguiente archivo:

```yaml
services:
  db:
    image: mcr.microsoft.com/mssql/server:2019-latest
    container_name: uct_sqlserver
    environment:
      - ACCEPT_EULA=Y
      - MSSQL_SA_PASSWORD=${MSSQL_SA_PASSWORD}
    ports:
      - "1433:1433"
    volumes:
      - sqlserver_data:/var/opt/mssql

  redis:
    image: redis:7-alpine
    container_name: uct_redis
    ports:
      - "6379:6379"

  api:
    build: 
      context: ./backend
      dockerfile: Dockerfile
    container_name: uct_fastapi
    depends_on:
      - db
      - redis
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-development}
      - DATABASE_URL=${DATABASE_URL}
      - DATABASE_URL_SYNC=${DATABASE_URL_SYNC}
      - REDIS_URL=${REDIS_URL:-redis://redis:6379/0}
      - FERNET_KEY=${FERNET_KEY}
    volumes:
      - ./backend:/app
      - ./Documentos_soloVista:/Documentos_soloVista:ro

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: uct_celery
    command: celery -A app.worker.celery_app worker --loglevel=info
    depends_on:
      - redis
      - db
    env_file:
      - .env
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-development}
      - DATABASE_URL=${DATABASE_URL}
      - DATABASE_URL_SYNC=${DATABASE_URL_SYNC}
      - REDIS_URL=${REDIS_URL:-redis://redis:6379/0}
      - FERNET_KEY=${FERNET_KEY}
    volumes:
      - ./backend:/app

volumes:
  sqlserver_data:
```

### `.env`
Debe contener la cadena de conexión de mínimo privilegio sobre `uct_dashboard`:
```dotenv
DATABASE_URL=mssql+aioodbc://${MSSQL_USUARIO_APP}:${MSSQL_CLAVE_APP}@db:1433/uct_dashboard?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
DATABASE_URL_SYNC=mssql+pyodbc://${MSSQL_USUARIO_APP}:${MSSQL_CLAVE_APP}@db:1433/uct_dashboard?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

### `frontend/.env.local`
```dotenv
VITE_API_URL=http://localhost:8000/api/v1
```

---

## 2. Inicialización del Backend (Docker)

1. **Levantar los contenedores**:
   ```bash
   docker-compose -f docker-compose.local.yml build
   docker-compose -f docker-compose.local.yml up -d
   ```

2. **Ejecutar migraciones de Base de Datos**:
   Es indispensable aplicar los esquemas en SQL Server, incluyendo los índices `COLUMNSTORE` (CCI) y Vistas Indexadas.
   
   > [!WARNING]
   > SQL Server puede demorar entre 15 y 20 segundos en iniciar completamente después de levantar el contenedor. Si ves el error `Login timeout expired`, simplemente espera unos segundos y vuelve a ejecutar el comando de abajo.

   ```bash
   docker-compose -f docker-compose.local.yml exec api alembic upgrade head
   ```

3. **Verificar Servicios**:
   Asegúrate de que la API y el Celery worker funcionen sin *crash loops*.
   ```bash
   docker logs uct_fastapi
   docker logs uct_celery
   ```
   *(Deberías ver los mensajes de inicialización correctos, como la carga de modelos y `celery@... ready`).*

---

## 3. Inicialización del Frontend (Nativo)

1. Abre una nueva terminal y accede a la carpeta `frontend`:
   ```bash
   cd frontend
   ```

2. Instala las dependencias y corre el servidor de desarrollo:
   ```bash
   npm install
   npm run dev
   ```

El Frontend estará disponible en `http://localhost:5173/`.

---

## Resultados de Validación Real
Durante el proceso de validación:
- **Drivers SQL Server**: Se configuró exitosamente `msodbcsql18` en Debian 12.
- **Backend Migrations**: Se implementaron los esquemas y vistas determinísticas de aforo con `SCHEMABINDING` en SQL Server.
- **Worker**: `uct_celery` conecta a Redis y la base de datos SQL Server desacoplado de `uct_fastapi`.
- **Frontend**: El servidor inicializa `Vite` exitosamente.

---

## 4. Poblado de Datos Inicial y Machine Learning

Es obligatorio ejecutar el siguiente comando la primera vez que levantes el proyecto para inyectar datos base y encolar las tareas de entrenamiento para los modelos predictivos de Machine Learning:

Ejecuta el script dentro del contenedor de la API:
```bash
docker exec -it uct_fastapi python scripts/seed_dashboard_data.py
```
