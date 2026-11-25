import logging
from datetime import date, timedelta
from typing import Iterable, List, Optional
from sqlalchemy import select, delete, text, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models import CalendarioAcademico, ContingenciaAcademica
from app.schemas.config_schemas import ContingenciaCrear
from app.adapters.base import CalendarEventDTO

logger = logging.getLogger(__name__)

# Solo tipos operativos deben aparecer como motivo de falta/incidencia en los gráficos
TIPOS_INCIDENCIA_OPERATIVA = {
    "falla_sensor",
    "apertura_manual",
    "mantencion_cierre",
    "suspension_sala",
    "sin_demanda",
    "otro",
}

ETIQUETAS_SUBESPACIO_CAL = {
    "sala_1": "Sala 1 (CSF02)",
    "sala_2": "Sala 2 (CSF04 Pecera)",
    "CSF11": "Estacionamiento CSF11",
    "CSF21": "Estacionamiento CSF21",
    "CHS01": "Estacionamiento CHS01",
}


def _formatear_segmento_contingencia(c: ContingenciaAcademica) -> str:
    subespacio_limpio = (getattr(c, "subespacio", None) or "todos").strip()
    prefijo_alcance = ""
    if subespacio_limpio != "todos":
        nombre_sub = ETIQUETAS_SUBESPACIO_CAL.get(subespacio_limpio, subespacio_limpio)
        prefijo_alcance = f"[{nombre_sub}] "
    elif getattr(c, "espacio_id", None) == 1:
        prefijo_alcance = "[Biblioteca] "
    elif getattr(c, "espacio_id", None) == 2:
        prefijo_alcance = "[Estacionamiento] "

    h_ini = (getattr(c, "hora_inicio", None) or "").strip()
    h_fin = (getattr(c, "hora_fin", None) or "").strip()
    rango_horas = ""
    if h_ini and h_fin:
        rango_horas = f" ({h_ini} a {h_fin} hrs)"
    elif h_ini:
        rango_horas = f" (desde {h_ini} hrs)"
    elif h_fin:
        rango_horas = f" (hasta {h_fin} hrs)"

    return f"{prefijo_alcance}[{c.titulo}{rango_horas}] {c.descripcion or ''}".strip()


def _extraer_segmentos_oficiales(descripcion: Optional[str]) -> list[str]:
    if not descripcion:
        return []
    return [
        seg.strip()
        for seg in str(descripcion).split("|")
        if seg.strip() and not seg.strip().startswith("[")
    ]


class CalendarService:
    async def bulk_insert_events(self, db: AsyncSession, dtos: List[CalendarEventDTO]):
        if not dtos:
            return
        try:
            for dto in dtos:
                item = CalendarioAcademico(
                    fecha=dto.fecha,
                    is_holiday=dto.is_holiday,
                    is_break=dto.is_break,
                    is_exam_period=dto.is_exam_period,
                    is_class_milestone=dto.is_class_milestone,
                    suspension_actividades=dto.suspension_actividades,
                    descripcion=dto.descripcion,
                    fuente=getattr(dto, "fuente", "scraping") or "scraping",
                )
                await db.merge(item)
            await db.commit()
            logger.info(f"[CalendarService] {len(dtos)} eventos de calendario insertados/actualizados.")
        except Exception as e:
            logger.error(f"[CalendarService] Error en bulk_insert_events: {e}")
            await db.rollback()
            raise

    async def obtener_contingencias(self, db: AsyncSession, anio: Optional[int] = None) -> List[ContingenciaAcademica]:
        query = select(ContingenciaAcademica).order_by(ContingenciaAcademica.fecha_inicio.desc())
        if anio:
            ini = date(anio, 1, 1)
            fin = date(anio, 12, 31)
            query = query.where(ContingenciaAcademica.fecha_inicio <= fin, ContingenciaAcademica.fecha_fin >= ini)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def reconciliar_dias_calendario(
        self,
        db: AsyncSession,
        fechas: Iterable[date],
        commit: bool = False,
    ) -> dict:
        """Recalcula las fechas indicadas en calendario_academico desde contingencias vigentes."""
        fechas_unicas = sorted(set(fechas))
        if not fechas_unicas:
            return {"actualizados": 0, "eliminados": 0}

        q_cont = (
            select(ContingenciaAcademica)
            .where(
                ContingenciaAcademica.fecha_inicio <= fechas_unicas[-1],
                ContingenciaAcademica.fecha_fin >= fechas_unicas[0],
            )
            .order_by(ContingenciaAcademica.id.asc())
        )
        conts_rango = list((await db.execute(q_cont)).scalars().all())

        actualizados = 0
        eliminados = 0
        for dia in fechas_unicas:
            conts_dia = [c for c in conts_rango if c.fecha_inicio <= dia <= c.fecha_fin]
            cal_item = await db.get(CalendarioAcademico, dia)

            if not conts_dia:
                if cal_item is None:
                    continue
                oficiales = _extraer_segmentos_oficiales(cal_item.descripcion)
                tiene_hito_oficial = bool(
                    cal_item.is_holiday
                    or cal_item.is_break
                    or cal_item.is_exam_period
                    or getattr(cal_item, "is_class_milestone", False)
                    or oficiales
                )
                if not tiene_hito_oficial:
                    await db.delete(cal_item)
                    eliminados += 1
                else:
                    cal_item.is_strike_federado = False
                    cal_item.is_strike_carrera = False
                    cal_item.tipo_contingencia = None
                    cal_item.descripcion = " | ".join(oficiales) if oficiales else None
                    cal_item.suspension_actividades = bool(
                        cal_item.is_holiday or any("suspensi" in s.lower() for s in oficiales)
                    )
                    actualizados += 1
            else:
                if cal_item is None:
                    cal_item = CalendarioAcademico(
                        fecha=dia,
                        is_holiday=False,
                        is_break=False,
                        is_exam_period=False,
                        is_class_milestone=False,
                        suspension_actividades=False,
                        fuente="contingencia_manual",
                    )
                    db.add(cal_item)

                oficiales = _extraer_segmentos_oficiales(cal_item.descripcion)
                cal_item.is_strike_federado = any(
                    (c.tipo or "").strip().lower() == "paro_federado" for c in conts_dia
                )
                cal_item.is_strike_carrera = any(
                    (c.tipo or "").strip().lower() == "paro_carrera" for c in conts_dia
                )
                cal_item.tipo_contingencia = conts_dia[-1].tipo
                cierre_oficial = bool(
                    cal_item.is_holiday or any("suspensi" in s.lower() for s in oficiales)
                )
                cierre_cont = any(bool(c.implica_cierre_total) for c in conts_dia)
                cal_item.suspension_actividades = bool(cierre_oficial or cierre_cont)

                segmentos = list(oficiales)
                for c in conts_dia:
                    seg_c = _formatear_segmento_contingencia(c)
                    if seg_c and seg_c not in segmentos:
                        segmentos.append(seg_c)
                cal_item.descripcion = " | ".join(segmentos) if segmentos else None
                actualizados += 1

        if commit:
            await db.commit()
        return {"actualizados": actualizados, "eliminados": eliminados}

    async def sanear_calendario_contingencias(self, db: AsyncSession) -> dict:
        """Elimina huérfanas y resincroniza calendario_academico con contingencias_academicas."""
        q_cal = select(CalendarioAcademico.fecha).where(
            or_(
                CalendarioAcademico.fuente == "contingencia_manual",
                CalendarioAcademico.tipo_contingencia.isnot(None),
                CalendarioAcademico.descripcion.like("%[%"),
            )
        )
        fechas_cal = (await db.execute(q_cal)).scalars().all()
        q_cont = select(ContingenciaAcademica.fecha_inicio, ContingenciaAcademica.fecha_fin)
        rangos_cont = (await db.execute(q_cont)).all()

        fechas: set[date] = set(fechas_cal)
        for f_ini, f_fin in rangos_cont:
            cur = f_ini
            while cur <= f_fin:
                fechas.add(cur)
                cur += timedelta(days=1)

        return await self.reconciliar_dias_calendario(db, fechas, commit=True)

    async def crear_contingencia(self, db: AsyncSession, data: ContingenciaCrear) -> ContingenciaAcademica:
        subespacio_limpio = (data.subespacio or "todos").strip()
        nueva = ContingenciaAcademica(
            fecha_inicio=data.fecha_inicio,
            fecha_fin=data.fecha_fin,
            tipo=data.tipo,
            titulo=data.titulo,
            descripcion=data.descripcion,
            espacio_id=data.espacio_id,
            subespacio=subespacio_limpio,
            hora_inicio=data.hora_inicio,
            hora_fin=data.hora_fin,
            carreras_afectadas=data.carreras_afectadas,
            implica_cierre_total=data.implica_cierre_total,
        )
        db.add(nueva)
        await db.flush()

        fechas: list[date] = []
        cur = data.fecha_inicio
        while cur <= data.fecha_fin:
            fechas.append(cur)
            cur += timedelta(days=1)

        await self.reconciliar_dias_calendario(db, fechas, commit=False)
        await db.commit()
        await db.refresh(nueva)
        return nueva

    async def eliminar_contingencia(self, db: AsyncSession, contingencia_id: int) -> bool:
        contingencia = await db.get(ContingenciaAcademica, contingencia_id)
        if not contingencia:
            return False

        fechas: list[date] = []
        cur = contingencia.fecha_inicio
        while cur <= contingencia.fecha_fin:
            fechas.append(cur)
            cur += timedelta(days=1)

        await db.delete(contingencia)
        # Flush previo para excluir la contingencia borrada antes de reconciliar
        await db.flush()
        await self.reconciliar_dias_calendario(db, fechas, commit=False)
        await db.commit()
        return True

    async def obtener_resumen_anual_calendario(self, db: AsyncSession, anio: int):
        ini = date(anio, 1, 1)
        fin = date(anio, 12, 31)
        query = select(CalendarioAcademico).where(
            CalendarioAcademico.fecha >= ini,
            CalendarioAcademico.fecha <= fin
        ).order_by(CalendarioAcademico.fecha.asc())
        rows = (await db.execute(query)).scalars().all()

        # Consultar contingencias del año para mapear aislamiento por sala/sector y garantizar propagación inmediata
        q_cont = select(ContingenciaAcademica).where(
            ContingenciaAcademica.fecha_inicio <= fin,
            ContingenciaAcademica.fecha_fin >= ini,
        )
        contingencias_anio = (await db.execute(q_cont)).scalars().all()
        mapa_subespacios: dict[date, list[str]] = {}
        mapa_espacios: dict[date, list[int]] = {}
        mapa_contingencia_cierre: dict[date, bool] = {}
        mapa_contingencia_paro_fed: dict[date, bool] = {}
        mapa_contingencia_paro_car: dict[date, bool] = {}
        mapa_contingencia_desc: dict[date, list[str]] = {}
        mapa_incidencias: dict[date, list[dict]] = {}

        etiquetas_sub = {
            "sala_1": "Sala 1 (CSF02)",
            "sala_2": "Sala 2 (CSF04 Pecera)",
            "CSF11": "Estacionamiento CSF11",
            "CSF21": "Estacionamiento CSF21",
            "CHS01": "Estacionamiento CHS01",
        }

        for c in contingencias_anio:
            d_cur = max(c.fecha_inicio, ini)
            d_end = min(c.fecha_fin, fin)
            sub_val = (getattr(c, "subespacio", None) or "todos").strip()
            esp_val = getattr(c, "espacio_id", None)
            h_ini = getattr(c, "hora_inicio", None)
            h_fin = getattr(c, "hora_fin", None)

            pref = f"[{etiquetas_sub.get(sub_val, sub_val)}] " if sub_val != "todos" else ""
            rango_h = f" ({h_ini} a {h_fin} hrs)" if (h_ini and h_fin) else ""
            texto_c = f"{pref}[{c.titulo}{rango_h}] {c.descripcion or ''}".strip()
            incidencia_dict = {
                "id": c.id,
                "tipo": c.tipo,
                "titulo": c.titulo,
                "descripcion": c.descripcion,
                "espacio_id": int(esp_val) if esp_val is not None else None,
                "subespacio": sub_val,
                "hora_inicio": h_ini,
                "hora_fin": h_fin,
                "implica_cierre_total": bool(c.implica_cierre_total),
            }

            es_incidencia_operativa = (c.tipo or "").strip().lower() in TIPOS_INCIDENCIA_OPERATIVA

            while d_cur <= d_end:
                mapa_subespacios.setdefault(d_cur, [])
                if sub_val not in mapa_subespacios[d_cur]:
                    mapa_subespacios[d_cur].append(sub_val)
                if esp_val is not None:
                    mapa_espacios.setdefault(d_cur, [])
                    if int(esp_val) not in mapa_espacios[d_cur]:
                        mapa_espacios[d_cur].append(int(esp_val))
                if c.implica_cierre_total or c.tipo in ("suspension_sala", "mantencion_cierre", "toma_campus", "climatica", "duelo"):
                    mapa_contingencia_cierre[d_cur] = True
                if c.tipo == "paro_federado":
                    mapa_contingencia_paro_fed[d_cur] = True
                elif c.tipo == "paro_carrera":
                    mapa_contingencia_paro_car[d_cur] = True
                mapa_contingencia_desc.setdefault(d_cur, [])
                if texto_c not in mapa_contingencia_desc[d_cur]:
                    mapa_contingencia_desc[d_cur].append(texto_c)
                if es_incidencia_operativa:
                    mapa_incidencias.setdefault(d_cur, []).append(incidencia_dict)
                d_cur += timedelta(days=1)

        mapa_rows = {r.fecha: r for r in rows}
        todas_fechas = sorted(set(mapa_rows.keys()) | set(mapa_subespacios.keys()))

        resultado = []
        for f_dia in todas_fechas:
            r = mapa_rows.get(f_dia)
            is_holiday = bool(r.is_holiday) if r else False
            is_break = bool(r.is_break) if r else False
            is_exam_period = bool(r.is_exam_period) if r else False
            is_class_milestone = bool(getattr(r, "is_class_milestone", False)) if r else False
            is_strike_federado = bool(getattr(r, "is_strike_federado", False)) if r else False
            is_strike_carrera = bool(getattr(r, "is_strike_carrera", False)) if r else False
            suspension_actividades = bool(r.suspension_actividades) if r else False
            descripcion = r.descripcion if r else None

            if mapa_contingencia_cierre.get(f_dia):
                suspension_actividades = True
            if mapa_contingencia_paro_fed.get(f_dia):
                is_strike_federado = True
            if mapa_contingencia_paro_car.get(f_dia):
                is_strike_carrera = True
            if f_dia in mapa_contingencia_desc:
                textos_extra = " | ".join(mapa_contingencia_desc[f_dia])
                if not descripcion:
                    descripcion = textos_extra
                else:
                    for t_item in mapa_contingencia_desc[f_dia]:
                        if t_item not in descripcion:
                            descripcion = f"{descripcion} | {t_item}"

            es_cierre = bool(is_holiday or is_break or suspension_actividades)
            es_paro = bool(is_strike_federado or is_strike_carrera)
            
            tipo_dia = "operativo"
            if is_holiday:
                tipo_dia = "feriado"
            elif is_break:
                tipo_dia = "receso"
            elif is_strike_federado:
                tipo_dia = "paro_federado"
            elif is_strike_carrera:
                tipo_dia = "paro_carrera"
            elif suspension_actividades:
                tipo_dia = "suspension"
            elif is_exam_period:
                tipo_dia = "examen"
            elif is_class_milestone:
                tipo_dia = "clases"

            resultado.append({
                "fecha": f_dia.isoformat(),
                "tipo_dia": tipo_dia,
                "es_cierre": es_cierre,
                "es_paro": es_paro,
                "is_holiday": is_holiday,
                "is_break": is_break,
                "is_exam_period": is_exam_period,
                "is_class_milestone": is_class_milestone,
                "is_strike_federado": is_strike_federado,
                "is_strike_carrera": is_strike_carrera,
                "suspension_actividades": suspension_actividades,
                "subespacios_suspendidos": mapa_subespacios.get(f_dia, []),
                "espacios_suspendidos": mapa_espacios.get(f_dia, []),
                "descripcion": descripcion,
                "incidencias_operativas": mapa_incidencias.get(f_dia, []),
            })
        return resultado

    async def obtener_eventos_calendario(
        self,
        db: AsyncSession,
        anio: Optional[int] = None,
        categoria: Optional[str] = None,
        busqueda: Optional[str] = None,
        agrupar_periodos: bool = True,
    ) -> List[dict]:
        query = select(CalendarioAcademico)

        if anio:
            ini = date(anio, 1, 1)
            fin = date(anio, 12, 31)
            query = query.where(CalendarioAcademico.fecha >= ini, CalendarioAcademico.fecha <= fin)

        if busqueda and busqueda.strip():
            b = f"%{busqueda.strip()}%"
            query = query.where(CalendarioAcademico.descripcion.ilike(b))

        if categoria:
            cat = categoria.strip().lower()
            if cat == "feriado":
                query = query.where(CalendarioAcademico.is_holiday == True)
            elif cat == "receso":
                query = query.where(CalendarioAcademico.is_break == True)
            elif cat == "examen":
                query = query.where(CalendarioAcademico.is_exam_period == True)
            elif cat == "clases":
                query = query.where(CalendarioAcademico.is_class_milestone == True)
            elif cat == "suspension":
                query = query.where(CalendarioAcademico.suspension_actividades == True)
            elif cat == "paro":
                query = query.where(
                    (CalendarioAcademico.is_strike_federado == True) | 
                    (CalendarioAcademico.is_strike_carrera == True)
                )

        query = query.order_by(CalendarioAcademico.fecha.asc())
        rows = (await db.execute(query)).scalars().all()

        resultado = []
        for r in rows:
            tipo_dia = "operativo"
            if r.is_holiday:
                tipo_dia = "feriado"
            elif r.is_break:
                tipo_dia = "receso"
            elif getattr(r, "is_strike_federado", False):
                tipo_dia = "paro_federado"
            elif getattr(r, "is_strike_carrera", False):
                tipo_dia = "paro_carrera"
            elif r.suspension_actividades:
                tipo_dia = "suspension"
            elif r.is_exam_period:
                tipo_dia = "examen"
            elif getattr(r, "is_class_milestone", False):
                tipo_dia = "clases"

            resultado.append({
                "fecha": r.fecha.isoformat(),
                "fecha_inicio": r.fecha.isoformat(),
                "fecha_fin": r.fecha.isoformat(),
                "dias_totales": 1,
                "tipo_dia": tipo_dia,
                "es_cierre": bool(r.is_holiday or r.is_break or r.suspension_actividades),
                "es_paro": bool(getattr(r, "is_strike_federado", False) or getattr(r, "is_strike_carrera", False)),
                "is_holiday": r.is_holiday,
                "is_break": r.is_break,
                "is_exam_period": r.is_exam_period,
                "is_class_milestone": getattr(r, "is_class_milestone", False),
                "is_strike_federado": getattr(r, "is_strike_federado", False),
                "is_strike_carrera": getattr(r, "is_strike_carrera", False),
                "suspension_actividades": r.suspension_actividades,
                "descripcion": r.descripcion,
                "fuente": getattr(r, "fuente", "scraping") or "scraping",
            })

        if not agrupar_periodos:
            return resultado

        # Consolidar días contiguos de la misma categoría en un solo período
        periodos = []
        for item in resultado:
            curr_date = date.fromisoformat(item["fecha"])
            if periodos:
                ultimo = periodos[-1]
                fin_date = date.fromisoformat(ultimo["fecha_fin"])
                es_contiguo = (curr_date - fin_date).days == 1
                mismo_tipo = ultimo["tipo_dia"] == item["tipo_dia"]

                if es_contiguo and mismo_tipo:
                    ultimo["fecha_fin"] = item["fecha"]
                    ultimo["dias_totales"] += 1

                    # Unificar descripciones sin redundancias
                    d1 = (ultimo["descripcion"] or "").strip()
                    d2 = (item["descripcion"] or "").strip()
                    if d1 and d2 and d1.lower() != d2.lower():
                        if d1.lower() in d2.lower():
                            ultimo["descripcion"] = d2
                        elif d2.lower() not in d1.lower():
                            ultimo["descripcion"] = f"{d1} • {d2}"
                    continue

            nuevo_periodo = dict(item)
            periodos.append(nuevo_periodo)

        return periodos

    async def depurar_calendario_basura(self, db: AsyncSession) -> int:
        stmt = text("""
            DELETE FROM calendario_academico
            WHERE is_holiday = 0 
              AND is_break = 0 
              AND is_exam_period = 0 
              AND is_class_milestone = 0 
              AND suspension_actividades = 0 
              AND (is_strike_federado IS NULL OR is_strike_federado = 0)
              AND (is_strike_carrera IS NULL OR is_strike_carrera = 0)
              AND (fuente IS NULL OR fuente = 'scraping')
        """)
        res = await db.execute(stmt)
        await db.commit()
        res_san = await self.sanear_calendario_contingencias(db)
        total = int(res.rowcount or 0) + int(res_san.get("eliminados", 0))
        logger.info(f"[CalendarService] Depuración completada: {total} registros basura/huérfanos eliminados.")
        return total

    async def actualizar_evento_calendario(
        self,
        db: AsyncSession,
        fecha: date,
        descripcion: str,
        is_holiday: bool,
        is_break: bool,
        is_exam_period: bool,
        is_class_milestone: bool,
        suspension_actividades: bool,
        is_strike_federado: bool = False,
        is_strike_carrera: bool = False,
        tipo_contingencia: Optional[str] = None,
    ) -> CalendarioAcademico:
        item = await db.get(CalendarioAcademico, fecha)
        if not item:
            item = CalendarioAcademico(fecha=fecha)
            db.add(item)

        item.descripcion = descripcion
        item.is_holiday = is_holiday
        item.is_break = is_break
        item.is_exam_period = is_exam_period
        item.is_class_milestone = is_class_milestone
        item.suspension_actividades = suspension_actividades
        item.is_strike_federado = is_strike_federado
        item.is_strike_carrera = is_strike_carrera
        item.tipo_contingencia = tipo_contingencia
        item.fuente = "manual"

        await db.commit()
        await db.refresh(item)
        return item

    async def crear_evento_calendario(
        self,
        db: AsyncSession,
        fecha_inicio: date,
        fecha_fin: date,
        descripcion: str,
        is_holiday: bool,
        is_break: bool,
        is_exam_period: bool,
        is_class_milestone: bool,
        suspension_actividades: bool,
        is_strike_federado: bool = False,
        is_strike_carrera: bool = False,
        tipo_contingencia: Optional[str] = None,
    ) -> List[CalendarioAcademico]:
        items = []
        cur = fecha_inicio
        while cur <= fecha_fin:
            item = await db.get(CalendarioAcademico, cur)
            if not item:
                item = CalendarioAcademico(fecha=cur)
                db.add(item)
            item.descripcion = descripcion
            item.is_holiday = is_holiday
            item.is_break = is_break
            item.is_exam_period = is_exam_period
            item.is_class_milestone = is_class_milestone
            item.suspension_actividades = suspension_actividades
            item.is_strike_federado = is_strike_federado
            item.is_strike_carrera = is_strike_carrera
            item.tipo_contingencia = tipo_contingencia
            item.fuente = "manual"
            items.append(item)
            cur += timedelta(days=1)

        await db.commit()
        return items

    async def eliminar_evento_calendario(self, db: AsyncSession, fecha: date) -> bool:
        item = await db.get(CalendarioAcademico, fecha)
        if not item:
            return False
        await db.delete(item)
        await db.commit()
        return True
