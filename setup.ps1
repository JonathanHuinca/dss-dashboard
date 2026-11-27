docker compose down -v
docker compose build backend
docker compose up -d --wait
docker compose exec backend alembic upgrade head
docker compose restart backend
Start-Sleep -Seconds 5
docker compose exec backend python -m app.cli seed-data
docker compose exec timescaledb psql -U uct_admin -d uct_dashboard -c "CALL refresh_continuous_aggregate('aforo_horario_biblioteca', NULL, NULL);"
docker compose exec timescaledb psql -U uct_admin -d uct_dashboard -c "CALL refresh_continuous_aggregate('aforo_horario_estacionamiento', NULL, NULL);"
docker compose exec backend python -m app.cli train-models
