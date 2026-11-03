import logging
from datetime import date, timedelta
from typing import List, Optional
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models import CalendarioAcademico, ContingenciaAcademica
from app.schemas.config_schemas import ContingenciaCrear
from app.adapters.base import CalendarEventDTO

logger = logging.getLogger(__name__)


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

        etiquetas_sub = {
            "sala_1": "Sala 1 (CSF02)",
            "sala_2": "Sala 2 (CSF04 Pecera)",
            "CSF11": "Estacionamiento CSF11",
            "CSF21": "Estacionamiento CSF21",
            "CHS01": "Estacionamiento CHS01",
        }
        prefijo_alcance = ""
        if subespacio_limpio != "todos":
            nombre_sub = etiquetas_sub.get(subespacio_limpio, subespacio_limpio)
            prefijo_alcance = f"[{nombre_sub}] "
        elif data.espacio_id == 1:
            prefijo_alcance = "[Biblioteca] "
        elif data.espacio_id == 2:
            prefijo_alcance = "[Estacionamiento] "

        rango_horas = ""
        if data.hora_inicio and data.hora_fin:
            rango_horas = f" ({data.hora_inicio} a {data.hora_fin} hrs)"

        # Propagar a calendario_academico para cada día del rango
        cur = data.fecha_inicio
        while cur <= data.fecha_fin:
            cal_item = await db.get(CalendarioAcademico, cur)
            if not cal_item:
                cal_item = CalendarioAcademico(
                    fecha=cur,
                    is_holiday=False,
                    is_break=False,
                    is_exam_period=False,
                    is_class_milestone=False,
                    suspension_actividades=False,
                    fuente="contingencia_manual",
                )
                db.add(cal_item)

            if data.tipo == "paro_federado":
                cal_item.is_strike_federado = True
            elif data.tipo == "paro_carrera":
                cal_item.is_strike_carrera = True
            
            cal_item.tipo_contingencia = data.tipo
            if data.implica_cierre_total:
                cal_item.suspension_actividades = True

            detalle = f"{prefijo_alcance}[{data.titulo}{rango_horas}] {data.descripcion or ''}".strip()
            if cal_item.descripcion:
                segmentos = [
                    s.strip()
                    for s in cal_item.descripcion.split("|")
                    if s.strip() and data.titulo not in s
                ]
                segmentos.append(detalle)
                cal_item.descripcion = " | ".join(segmentos)
            else:
                cal_item.descripcion = detalle

            cur += timedelta(days=1)

        await db.commit()
        await db.refresh(nueva)
        return nueva

    async def eliminar_contingencia(self, db: AsyncSession, contingencia_id: int) -> bool:
        contingencia = await db.get(ContingenciaAcademica, contingencia_id)
        if not contingencia:
            return False

        # Desmarcar días en calendario_academico y limpiar descripción asociada
        cur = contingencia.fecha_inicio
        while cur <= contingencia.fecha_fin:
            cal_item = await db.get(CalendarioAcademico, cur)
            if cal_item:
                if contingencia.tipo == "paro_federado":
                    cal_item.is_strike_federado = False
                elif contingencia.tipo == "paro_carrera":
                    cal_item.is_strike_carrera = False
                if contingencia.implica_cierre_total:
                    cal_item.suspension_actividades = False
                cal_item.tipo_contingencia = None
                if cal_item.descripcion and contingencia.titulo in cal_item.descripcion:
                    segmentos = [
                        s.strip()
                        for s in cal_item.descripcion.split("|")
                        if s.strip() and contingencia.titulo not in s
                    ]
                    cal_item.descripcion = " | ".join(segmentos) if segmentos else None
                if (
                    not cal_item.is_holiday
                    and not cal_item.is_break
                    and not cal_item.is_exam_period
                    and not getattr(cal_item, "is_class_milestone", False)
                    and not cal_item.suspension_actividades
                    and not getattr(cal_item, "is_strike_federado", False)
                    and not getattr(cal_item, "is_strike_carrera", False)
                    and not cal_item.descripcion
                ):
                    await db.delete(cal_item)
            cur += timedelta(days=1)

        await db.delete(contingencia)
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

            while d_cur <= d_end:
                mapa_subespacios.setdefault(d_cur, [])
                if sub_val not in mapa_subespacios[d_cur]:
                    mapa_subespacios[d_cur].append(sub_val)
                if esp_val is not None:
                    mapa_espacios.setdefault(d_cur, [])
                    if int(esp_val) not in mapa_espacios[d_cur]:
                        mapa_espacios[d_cur].append(int(esp_val))
                if c.implica_cierre_total or c.tipo in ("suspension_sala", "toma_campus", "climatica", "duelo"):
                    mapa_contingencia_cierre[d_cur] = True
                if c.tipo == "paro_federado":
                    mapa_contingencia_paro_fed[d_cur] = True
                elif c.tipo == "paro_carrera":
                    mapa_contingencia_paro_car[d_cur] = True
                mapa_contingencia_desc.setdefault(d_cur, [])
                if texto_c not in mapa_contingencia_desc[d_cur]:
                    mapa_contingencia_desc[d_cur].append(texto_c)
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
        logger.info(f"[CalendarService] Depuración completada: {res.rowcount} registros basura eliminados.")
        return res.rowcount

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
