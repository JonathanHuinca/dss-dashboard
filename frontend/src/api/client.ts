/**
 * client.ts — Fachada principal de la API del Frontend DSS UCT.
 * 
 * Re-exporta los submódulos especializados para preservar compatibilidad funcional:
 * - clienteBase.ts: Instancia Axios, interceptores JWT y tipos comunes.
 * - asistencia.ts: Métricas, KPIs, aforo y analítica de asistencia peatonal.
 * - vehiculos.ts: KPIs vehiculares, estacionamientos por sector y clusters ANPR.
 * - prediccion.ts: Modelos Prophet, GBR, perfiles de visita y alertas.
 * - asistente.ts: Chat analítico interactivo, streaming SSE y cuotas IA.
 * - administracion.ts: Tareas programadas, Smart Campus, calendario, usuarios e ingesta.
 */

export * from './clienteBase'
export * from './asistencia'
export * from './vehiculos'
export * from './prediccion'
export * from './asistente'
export * from './administracion'
export * from './reportesCompartidos'
