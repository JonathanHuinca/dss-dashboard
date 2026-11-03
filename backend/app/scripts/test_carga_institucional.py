"""
Script de prueba para validar la ingesta del esquema institucional UCT (11 tablas + SCD-2 + sincronización dim_estudiante_carrera).
"""
import asyncio
import io
from datetime import datetime, date
from pathlib import Path
import openpyxl
import pandas as pd
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import pseudonymize_person
from app.core.security_cipher import encrypt_api_key
from app.domain.models import DimEstudianteCarrera
from app.domain.modelos_institucionales_uct import (
    InstitucionalCampus,
    InstitucionalEdificios,
    InstitucionalTipoInmueble,
    InstitucionalAmbiente,
    InstitucionalTipoCarrera,
    InstitucionalCarreraPrograma,
    InstitucionalCarreraCampus,
    InstitucionalSituacionAlumno,
    InstitucionalViasIngreso,
    InstitucionalEstudiante,
    InstitucionalEstudianteCarrera,
)


def _parse_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    val_s = str(val).strip()
    if not val_s or val_s.lower() in ("null", "none", "nan", ""):
        return None
    try:
        return datetime.fromisoformat(val_s.split(".")[0])
    except Exception:
        try:
            return pd.to_datetime(val_s).to_pydatetime()
        except Exception:
            return None


def _parse_date(val):
    dt = _parse_dt(val)
    return dt.date() if dt else None


async def test_carga():
    excel_path = Path("/app/DATOS_PRUEBAS_INSTITUCIONALES_UCT.xlsx")
    if not excel_path.exists():
        excel_path = Path(r"c:\Users\jonaw\Documents\__Tesis\Proyecto_dashboard_api_geminis\biblioteca\datos_estudiante\DATOS_PRUEBAS_INSTITUCIONALES_UCT.xlsx")
    wb = openpyxl.load_workbook(excel_path, data_only=True)

    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        print("Conectado a BD. Iniciando purga institucional previa...")
        await db.execute(delete(DimEstudianteCarrera))
        await db.execute(delete(InstitucionalEstudianteCarrera))
        await db.execute(delete(InstitucionalEstudiante))
        await db.execute(delete(InstitucionalCarreraCampus))
        await db.execute(delete(InstitucionalCarreraPrograma))
        await db.execute(delete(InstitucionalTipoCarrera))
        await db.execute(delete(InstitucionalSituacionAlumno))
        await db.execute(delete(InstitucionalViasIngreso))
        await db.execute(delete(InstitucionalAmbiente))
        await db.execute(delete(InstitucionalEdificios))
        await db.execute(delete(InstitucionalTipoInmueble))
        await db.execute(delete(InstitucionalCampus))
        await db.commit()

        # 1. CAMPUS
        print("Procesando CAMPUS...")
        ws_camp = wb["CAMPUS"]
        campus_ids = set()
        campus_items = []
        for r in list(ws_camp.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                c_id = int(r[0])
                campus_ids.add(c_id)
                campus_items.append(
                    InstitucionalCampus(
                        camp_codigo_campus=c_id,
                        camp_campus=str(r[1] or "").strip(),
                        camp_direccion=str(r[2] or "").strip() or None,
                        camp_vigente=str(r[3] or "S").strip()[:1],
                        camp_fecha_registro=_parse_dt(r[4]),
                        camp_usuario=str(r[5] or "").strip() or None,
                    )
                )
        db.add_all(campus_items)
        await db.commit()
        print(f"CAMPUS insertados: {len(campus_items)}")

        # 2. TIPO_INMUEBLE
        print("Procesando tipo_inmueble...")
        ws_ti = wb["relacionadas con ambiente"]
        ti_items = []
        for r in list(ws_ti.iter_rows(values_only=True))[3:]:
            if r[0] is None:
                continue
            val_0 = str(r[0]).strip()
            if not val_0.isdigit():
                if "TABLA:" in val_0.upper():
                    break
                continue
            ti_items.append(
                InstitucionalTipoInmueble(
                    tiin_codigo=int(val_0),
                    tiin_nombre=str(r[1] or "").strip(),
                    tiin_descripcion=str(r[2] or "").strip() or None,
                    tiin_vigente=str(r[3] or "S").strip()[:1],
                    usuario_mod=str(r[4] or "").strip() or None,
                    fecha_mod=_parse_dt(r[5]),
                )
            )
        db.add_all(ti_items)
        await db.commit()
        print(f"tipo_inmueble insertados: {len(ti_items)}")

        # 3. EDIFICIOS (con placeholders de campus faltantes si los hay)
        print("Procesando EDIFICIOS...")
        ws_ed = wb["EDIFICIOS"]
        ed_rows = [r for r in list(ws_ed.iter_rows(values_only=True))[3:] if r[0] is not None]
        needed_camp_fks = {int(r[1]) for r in ed_rows if r[1] is not None}
        missing_camp = needed_camp_fks - campus_ids
        if missing_camp:
            print(f"Insertando placeholders para campus faltantes en EDIFICIOS: {missing_camp}")
            for mc in missing_camp:
                db.add(InstitucionalCampus(
                    camp_codigo_campus=mc,
                    camp_campus=f"CAMPUS EXTERNO / NO ESPECIFICADO {mc}",
                    camp_vigente="N",
                    camp_usuario="sistema_ingesta",
                ))
                campus_ids.add(mc)
            await db.commit()

        ed_items = []
        for r in ed_rows:
            ed_items.append(
                InstitucionalEdificios(
                    edif_codigo_edificio=int(r[0]),
                    camp_codigo_campus=int(r[1]),
                    edif_edificio=str(r[2] or "").strip(),
                    edif_vigente=str(r[3] or "S").strip()[:1],
                    edif_observacion=str(r[4] or "").strip() or None,
                    edif_fecha_registro=_parse_dt(r[5]),
                    edif_usuario=str(r[6] or "").strip() or None,
                )
            )
        db.add_all(ed_items)
        await db.commit()
        print(f"EDIFICIOS insertados: {len(ed_items)}")

        # 4. AMBIENTE
        print("Procesando AMBIENTE...")
        ws_amb = wb["AMBIENTE"]
        amb_items = []
        for r in list(ws_amb.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                amb_items.append(
                    InstitucionalAmbiente(
                        ambi_codigo=int(r[0]),
                        camp_codigo=int(r[1]) if r[1] is not None else None,
                        inmu_codigo=int(r[2]) if r[2] is not None else None,
                        nive_codigo=int(r[3]) if r[3] is not None else None,
                        tami_codigo=int(r[4]) if r[4] is not None else None,
                        ambi_nombre=str(r[5] or "").strip(),
                        ambi_sigla_nuevo=str(r[6] or "").strip() or None,
                        ambi_vigente=str(r[7] or "S").strip()[:1],
                        usuario_mod=str(r[8] or "").strip() if len(r) > 8 and r[8] else None,
                        fecha_mod=_parse_dt(r[9]) if len(r) > 9 else None,
                    )
                )
        db.add_all(amb_items)
        await db.commit()
        print(f"AMBIENTE insertados: {len(amb_items)}")

        # 5. TIPO_CARRERA / CLASIFICACION_CARRERA
        print("Procesando tipo_carrera...")
        ws_tc = wb["relacio con carrera_programa"]
        tc_rows = list(ws_tc.iter_rows(values_only=True))[3:]
        tcar_dict = {}
        clac_dict = {}
        for r in tc_rows:
            if r[0] is not None and str(r[0]).strip().isdigit():
                tcar_dict[int(str(r[0]).strip())] = (str(r[1] or "").strip(), str(r[2] or "").strip())
            if len(r) > 6 and r[6] is not None and str(r[6]).strip().isdigit():
                clac_dict[int(str(r[6]).strip())] = (
                    str(r[7] or "").strip(),
                    str(r[8] or "").strip() if len(r) > 8 else None,
                    str(r[9] or "").strip() if len(r) > 9 else None,
                    _parse_dt(r[10]) if len(r) > 10 else None,
                )

        # Recoger pares en CARRERA_PROGRAMA
        ws_cp = wb["CARRERA_PROGRAMA"]
        cp_rows = [r for r in list(ws_cp.iter_rows(values_only=True))[3:] if r[0] is not None]
        fk_pairs = set()
        for r in cp_rows:
            if r[1] is not None and r[2] is not None:
                fk_pairs.add((int(r[1]), int(r[2])))

        # Combinar registros de tipo carrera para cubrir la PK compuesta (tcar_codigo, clac_codigo)
        tc_items = []
        for tcar_c, clac_c in fk_pairs:
            t_nom, t_tip = tcar_dict.get(tcar_c, ("PREGRADO", "1"))
            c_nom, c_desc, c_user, c_fec = clac_dict.get(clac_c, ("CARRERA", "CARRERA PROFESIONAL", "MIGRACION", None))
            tc_items.append(
                InstitucionalTipoCarrera(
                    tcar_codigo=tcar_c,
                    clac_codigo=clac_c,
                    tcar_nombre=t_nom,
                    tcar_tipo=t_tip,
                    clac_nombre=c_nom,
                    clac_descripcion=c_desc,
                    usuario_mod=c_user,
                    fecha_mod=c_fec,
                )
            )
        db.add_all(tc_items)
        await db.commit()
        print(f"tipo_carrera insertados: {len(tc_items)}")

        # 6. CARRERA_PROGRAMA
        print("Procesando CARRERA_PROGRAMA...")
        cp_items = []
        carrera_map = {}
        for r in cp_rows:
            c_cod = int(r[0])
            c_nom = str(r[3] or "").strip()
            carrera_map[c_cod] = c_nom
            cp_items.append(
                InstitucionalCarreraPrograma(
                    carr_codigo=c_cod,
                    tcar_codigo=int(r[1]) if r[1] is not None else None,
                    clac_codigo=int(r[2]) if r[2] is not None else None,
                    carr_nombre=c_nom,
                    uaca_codigo=int(r[4]) if r[4] is not None and str(r[4]).isdigit() else None,
                    uaca_codigo_dicta=int(r[5]) if r[5] is not None and str(r[5]).isdigit() else None,
                    usuario_mod=str(r[6] or "").strip() or None,
                    fecha_mod=_parse_dt(r[7]),
                )
            )
        db.add_all(cp_items)
        await db.commit()
        print(f"CARRERA_PROGRAMA insertados: {len(cp_items)}")

        # 7. CARRERA_CAMPUS
        print("Procesando CARRERA_CAMPUS...")
        ws_cc = wb["CARRERA_CAMPUS"]
        cc_items = []
        seen_cc = set()
        for r in list(ws_cc.iter_rows(values_only=True))[3:]:
            if r[0] is not None and r[1] is not None:
                pair = (int(r[0]), int(r[1]))
                if pair not in seen_cc:
                    seen_cc.add(pair)
                    cc_items.append(
                        InstitucionalCarreraCampus(
                            carr_codigo=pair[0],
                            camp_codigo=pair[1],
                            usuario_mod=str(r[2] or "").strip() or None,
                            fecha_mod=_parse_dt(r[3]),
                        )
                    )
        db.add_all(cc_items)
        await db.commit()
        print(f"CARRERA_CAMPUS insertados: {len(cc_items)}")

        # 8. SITUACION_ALUMNO
        print("Procesando SITUACION_ALUMNO...")
        ws_sa = wb["SITUACION_ALUMNO"]
        sa_items = []
        situacion_map = {}
        for r in list(ws_sa.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                s_cod = int(r[0])
                s_nom = str(r[1] or "").strip()
                situacion_map[s_cod] = s_nom
                sa_items.append(
                    InstitucionalSituacionAlumno(
                        salu_codigo=s_cod,
                        salu_nombre=s_nom,
                    )
                )
        db.add_all(sa_items)
        await db.commit()
        print(f"SITUACION_ALUMNO insertados: {len(sa_items)}")

        # 9. VIAS_INGRESO
        print("Procesando VIAS_INGRESO...")
        ws_vi = wb["VIAS_INGRESO"]
        vi_items = []
        for r in list(ws_vi.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                vi_items.append(
                    InstitucionalViasIngreso(
                        ving_codigo=int(r[0]),
                        ving_nombre=str(r[1] or "").strip(),
                        ving_descripcion=str(r[2] or "").strip() or None,
                        usuario_mod=str(r[3] or "").strip() or None,
                        fecha_mod=_parse_dt(r[4]),
                    )
                )
        db.add_all(vi_items)
        await db.commit()
        print(f"VIAS_INGRESO insertados: {len(vi_items)}")

        # 10. ESTUDIANTE (con Ley 21.719)
        print("Procesando ESTUDIANTE (Seudonimización y Cifrado)...")
        ws_est = wb["ESTUDIANTE"]
        est_items = []
        for r in list(ws_est.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                rut_raw = str(r[0]).strip()
                rut_h = pseudonymize_person(rut_raw)
                est_items.append(
                    InstitucionalEstudiante(
                        estd_rut_hash=rut_h,
                        estd_rut_cifrado=encrypt_api_key(rut_raw),
                        estd_dv=str(r[1] or "").strip()[:2] or None,
                        estd_paterno_cifrado=encrypt_api_key(str(r[2] or "").strip()) if r[2] else None,
                        estd_materno_cifrado=encrypt_api_key(str(r[3] or "").strip()) if r[3] else None,
                        estd_nombre1_cifrado=encrypt_api_key(str(r[4] or "").strip()) if r[4] else None,
                        estd_nombre2_cifrado=encrypt_api_key(str(r[5] or "").strip()) if r[5] else None,
                        sexo_codigo=str(r[6] or "").strip()[:10] if r[6] is not None else None,
                        estd_fecha_nac=_parse_date(r[7]),
                    )
                )
        db.add_all(est_items)
        await db.commit()
        print(f"ESTUDIANTE insertados: {len(est_items)}")

        # 11. ESTUDIANTE_CARRERA con SCD-2
        print("Procesando ESTUDIANTE_CARRERA (SCD-2)...")
        ws_ec = wb["ESTUDIANTE_CARRERA"]
        ec_items = []
        dim_items = []
        ahora = datetime.now()
        for r in list(ws_ec.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                reg_str = str(r[0]).strip()
                rut_str = str(r[1]).strip() if r[1] is not None else ""
                rut_h = pseudonymize_person(rut_str) if rut_str else None
                dv_s = str(r[2] or "").strip()[:2] or None
                c_cod = int(r[3]) if r[3] is not None else None
                p_cod = int(r[4]) if r[4] is not None else None
                m_cod = int(r[5]) if r[5] is not None else None
                s_cod = int(r[6]) if r[6] is not None else None
                v_cod = int(r[7]) if r[7] is not None else None
                a_ing = int(r[8]) if len(r) > 8 and r[8] is not None else None
                s_ing = int(r[9]) if len(r) > 9 and r[9] is not None else None
                t_imp = int(r[10]) if len(r) > 10 and r[10] is not None else None
                u_mod = str(r[11] or "").strip() or None if len(r) > 11 else None
                f_mod = _parse_dt(r[12]) if len(r) > 12 else None

                periodo = f"{a_ing}-{s_ing}" if a_ing and s_ing else "2026-1"

                ec_items.append(
                    InstitucionalEstudianteCarrera(
                        estu_registro=reg_str,
                        estd_rut_hash=rut_h,
                        estd_dv=dv_s,
                        carr_codigo=c_cod,
                        plan_codigo=p_cod,
                        men_codigo=m_cod,
                        salu_codigo=s_cod,
                        ving_codigo=v_cod,
                        estu_anho_ing=a_ing,
                        estu_semestre_ing=s_ing,
                        timp_codigo=t_imp,
                        periodo_academico=periodo,
                        fecha_desde=ahora,
                        fecha_hasta=None,
                        es_actual=True,
                        usuario_mod=u_mod,
                        fecha_mod=f_mod,
                    )
                )

                # Sincronización en dim_estudiante_carrera
                pid_h = pseudonymize_person(reg_str)
                c_nom = carrera_map.get(c_cod, "Sin carrera catalogada")
                dim_items.append(
                    DimEstudianteCarrera(
                        person_id_hash=pid_h,
                        matricula=reg_str,
                        rut_hash=rut_h,
                        carr_codigo=c_cod,
                        carr_nombre=c_nom,
                        facultad="Facultad UCT",
                        anho_ingreso=a_ing,
                        estamento="Estudiante",
                    )
                )

        batch_sz = 1000
        for i in range(0, len(ec_items), batch_sz):
            db.add_all(ec_items[i:i+batch_sz])
            await db.flush()
        await db.commit()
        print(f"ESTUDIANTE_CARRERA insertados: {len(ec_items)}")

        # Insertar dim_estudiante_carrera
        for i in range(0, len(dim_items), batch_sz):
            db.add_all(dim_items[i:i+batch_sz])
            await db.flush()
        await db.commit()
        print(f"dim_estudiante_carrera insertados: {len(dim_items)}")

        # Probar vista analítica
        res_vw = await db.execute(text("SELECT count(*) FROM vw_estudiante_carrera_actual"))
        print(f"Filas en vista vw_estudiante_carrera_actual: {res_vw.scalar()}")

    await engine.dispose()
    print("PROCESO DE CARGA EXITOSO Y SIN ERRORES.")


if __name__ == "__main__":
    asyncio.run(test_carga())
