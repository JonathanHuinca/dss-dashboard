# DSS Dashboard - UCT Campus San Francisco

Sistema de apoyo a la toma de decisiones (DSS) para la afluencia peatonal y vehicular en el Campus San Francisco de la Universidad Católica de Temuco. Integra análisis en tiempo real, modelos de Machine Learning (Prophet, Isolation Forest) y un Asistente de Inteligencia Artificial contextual basado en Google Gemini.

## Stack Tecnológico
- **Base de Datos Principal:** Microsoft SQL Server 2019 (CCI + RLS)
- **Planificador de Tareas:** APScheduler (en memoria y base de datos)
- **Backend:** FastAPI (Python 3.11+)
- **Frontend:** React + Vite + TypeScript (TailwindCSS, Plotly)

## Requisitos Previos
- [Docker](https://docs.docker.com/get-docker/) y [Docker Compose](https://docs.docker.com/compose/install/)

## Ejecución Local con Docker Compose

El proyecto está orquestado para ser levantado íntegramente mediante contenedores. Esto incluye los servicios de base de datos, el API del backend (con planificador interno APScheduler) y el frontend.

### Pasos para Iniciar el Stack

1. **Preparar el Archivo de Entorno**
   Asegúrate de copiar el archivo `.env.example` y nombrarlo `.env` en la raíz de tu proyecto. Valida que la variable de entorno principal esté en desarrollo:
   ```env
   ENVIRONMENT=development
   ```
   *Nota: Esto habilita el script de **Database Seeding** idempotente en FastAPI al iniciar.*

2. **Levantar los Contenedores**
   Ejecuta el siguiente comando para compilar y orquestar todas las imágenes en segundo plano:
   ```bash
   docker-compose up -d --build
   ```

3. **Comprobar el Estado de los Servicios**
   Verifica que la base de datos SQL Server 2019, el backend y el frontend estén correctamente provisionados y saludables:
   ```bash
   docker-compose ps
   ```

4. **Acceso a los Servicios**
   - **Frontend (Dashboard UI):** Navega a [http://localhost:3000](http://localhost:3000) (puerto por defecto).
   - **Backend API (Swagger UI):** Navega a [http://localhost:8000/docs](http://localhost:8000/docs) para interactuar directamente con los endpoints.
   - **Conexión SQL Server:** Accesible de forma local en `localhost:1433`.

5. **Monitoreo del Backend y Tareas Programadas**
   El reentrenamiento de modelos ML y la sincronización de calendarios se ejecutan mediante el planificador interno del backend:
   ```bash
   docker-compose logs -f api
   ```

6. **Detener el Stack**
   Para apagar el ambiente de forma segura, ejecuta:
   ```bash
   docker-compose down
   ```

---
> Para consultar los detalles internos, flujos de seguridad RLS e indexación (CCI), puedes referirte a la [Documentación de Arquitectura](ARCHITECTURE.md).
