"""
test_inspect.py — Prueba unitaria del motor de inspección previa y Schema Matching (RF03).
"""
import asyncio
import io
import pandas as pd
from app.services.ingestion_service import inspect_uploaded_file

async def run_tests():
    print("--- INICIANDO TEST 1: Asistencia con CSV estándar ---")
    csv_content = """Fecha,Primera entrada,Ultima salida,Door de entrada,Door de salida,Persona,Numero de matricula,Marcajes,Dif. salida (min)
2024-03-04,08:15:00,12:30:00,Acceso Norte,Acceso Norte,Juan Perez Gonzalez,2021001234,2,255
2024-03-04,09:00:00,10:15:00,Acceso Sur,Acceso Sur,Maria Lopez Silva,2022005678,1,75
"""
    res1 = await inspect_uploaded_file(
        file_bytes=csv_content.encode('utf-8'),
        filename="asistencia_prueba.csv",
        tipo="asistencia",
        espacio_id=1
    )
    print(f"Filename: {res1.filename}, Tipo: {res1.tipo}")
    print(f"Header row index: {res1.header_row_index}, Total rows: {res1.total_rows_estimated}")
    print(f"All required matched: {res1.all_required_matched}")
    assert res1.all_required_matched is True
    assert res1.total_rows_estimated == 2
    
    # Verificar que el preview no tenga PII
    for row in res1.preview_rows:
        persona_val = row.get("Persona")
        matricula_val = row.get("Numero de matricula")
        print(f"Sanitized row -> Persona: '{persona_val}', Matricula: '{matricula_val}'")
        assert persona_val == "[DATO PURGADO - LEY 21.719]", "La PII no fue purgada!"
        assert "EST-***" in matricula_val, "El identificador no fue enmascarado!"

    print("\n--- INICIANDO TEST 2: HikCentral con 6 filas de metadatos (Vehicular) ---")
    # Simular estructura de reporte HikCentral
    excel_buffer = io.BytesIO()
    # 6 filas de metadatos dummy antes de la cabecera real
    metadata = [
        ["Reporte:", "Paso Vehicular Campus San Francisco"],
        ["Fecha Inicio:", "2024-03-01"],
        ["Fecha Fin:", "2024-03-31"],
        ["Operador:", "Admin"],
        ["Total Registros:", "100"],
        [""],
    ]
    header = ["Hora", "Numero de matricula", "Dispositivo", "Direccion", "Tipo de vehiculo", "Marca", "Color"]
    data = [
        ["2024-03-04 08:30:00", "ABCD12", "Camara LPR 01", "Avanzar", "Automóvil", "Toyota", "Blanco"],
        ["2024-03-04 08:45:00", "WXYZ99", "Camara LPR 02", "Retroceder", "Camioneta", "Ford", "Gris"],
    ]
    all_rows = metadata + [header] + data
    df_excel = pd.DataFrame(all_rows)
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_excel.to_excel(writer, index=False, header=False)
        
    res2 = await inspect_uploaded_file(
        file_bytes=excel_buffer.getvalue(),
        filename="reporte_hikcentral_vehicular.xlsx",
        tipo="vehicular",
        espacio_id=2
    )
    print(f"Header row index detectado: {res2.header_row_index} (esperado 6)")
    print(f"Columnas detectadas: {res2.columns_detected}")
    print(f"All required matched: {res2.all_required_matched}")
    assert res2.header_row_index == 6, f"Se esperaba fila 6 y se detectó {res2.header_row_index}"
    assert res2.all_required_matched is True
    
    # Verificar semáforo: 'Numero de matricula' mapeado a 'Placa' (amarillo por sinónimo)
    placa_mapping = next(m for m in res2.schema_mapping if m.target_field == "Placa")
    print(f"Placa mapping: {placa_mapping.target_field} -> {placa_mapping.matched_column} ({placa_mapping.status})")
    assert placa_mapping.matched_column == "Numero de matricula"
    assert placa_mapping.status in ["amarillo", "verde"]
    
    # Verificar sanitización de patente
    for row in res2.preview_rows:
        pat_val = row.get("Numero de matricula")
        print(f"Sanitized row -> Patente: '{pat_val}'")
        assert "VEH-***" in pat_val or "[SEUDONIMIZADO]" in pat_val

    print("\n--- INICIANDO TEST 3: Archivo con columnas faltantes (Semáforo Rojo) ---")
    csv_incompleto = """Fecha,Persona
2024-03-04,Pedro Soto
"""
    res3 = await inspect_uploaded_file(
        file_bytes=csv_incompleto.encode('utf-8'),
        filename="incompleto.csv",
        tipo="asistencia",
        espacio_id=1
    )
    print(f"All required matched: {res3.all_required_matched} (esperado False)")
    print(f"Missing required fields: {res3.missing_required_fields}")
    assert res3.all_required_matched is False
    assert "Primera entrada" in res3.missing_required_fields
    assert "Numero de matricula" in res3.missing_required_fields

    print("\nTODOS LOS TESTS COMPLETADOS SATISFACTORIAMENTE!")

if __name__ == "__main__":
    asyncio.run(run_tests())
