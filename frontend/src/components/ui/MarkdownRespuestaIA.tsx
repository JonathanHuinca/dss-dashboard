import React from 'react'

type BloqueMarkdown =
  | { tipo: 'heading'; nivel: 1 | 2 | 3; texto: string }
  | { tipo: 'kpi_grid'; items: Array<{ etiqueta: string; valor: string }> }
  | { tipo: 'list'; ordenada: boolean; items: string[] }
  | { tipo: 'table'; encabezados: string[]; filas: string[][] }
  | { tipo: 'paragraph'; texto: string }

function parsearParClaveValor(item: string): { etiqueta: string; valor: string } | null {
  const m = item.match(/^\*\*([^*]+?)\*\*:?\s*(.+)$/)
  if (!m) return null
  const etiqueta = m[1].replace(/:+$/, '').trim()
  const valor = m[2].replace(/^:\s*/, '').trim()
  if (!etiqueta || !valor || etiqueta.length > 80) return null
  return { etiqueta, valor }
}

function esLineaTabla(linea: string): boolean {
  const trimmed = linea.trim()
  return trimmed.startsWith('|') && trimmed.includes('|', 1)
}

function esSeparadorTabla(linea: string): boolean {
  const trimmed = linea.trim()
  return /^\|?[\s:|-]+\|?$/.test(trimmed) && trimmed.includes('-')
}

function parsearCeldasTabla(linea: string): string[] {
  return linea
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim())
}

function parsearBloquesMarkdown(contenido: string): BloqueMarkdown[] {
  const lineas = contenido.replace(/\r\n/g, '\n').split('\n')
  const bloques: BloqueMarkdown[] = []
  let i = 0

  while (i < lineas.length) {
    const raw = lineas[i]
    const trimmed = raw.trim()

    if (!trimmed) {
      i += 1
      continue
    }

    // Encabezados (#, ##, ###)
    const mHead = trimmed.match(/^(#{1,3})\s+(.+)$/)
    if (mHead) {
      const nivel = Math.min(3, mHead[1].length) as 1 | 2 | 3
      bloques.push({ tipo: 'heading', nivel, texto: mHead[2].trim() })
      i += 1
      continue
    }

    // Tablas Markdown
    if (esLineaTabla(trimmed) && i + 1 < lineas.length && esSeparadorTabla(lineas[i + 1])) {
      const encabezados = parsearCeldasTabla(trimmed)
      i += 2
      const filas: string[][] = []
      while (i < lineas.length && esLineaTabla(lineas[i])) {
        filas.push(parsearCeldasTabla(lineas[i]))
        i += 1
      }
      bloques.push({ tipo: 'table', encabezados, filas })
      continue
    }

    // Listas con viñetas (* o -) y detección de fichas clave-valor
    if (/^(\*|-)\s+/.test(trimmed)) {
      const itemsRaw: string[] = []
      while (i < lineas.length) {
        const lt = lineas[i].trim()
        const mBullet = lt.match(/^(?:\*|-)\s+(.+)$/)
        if (!mBullet) break
        itemsRaw.push(mBullet[1].trim())
        i += 1
      }

      const pares = itemsRaw.map(parsearParClaveValor)
      if (itemsRaw.length >= 2 && pares.every((p): p is { etiqueta: string; valor: string } => p !== null)) {
        bloques.push({ tipo: 'kpi_grid', items: pares })
      } else {
        bloques.push({ tipo: 'list', ordenada: false, items: itemsRaw })
      }
      continue
    }

    // Listas numeradas (1. , 2. )
    if (/^\d+\.\s+/.test(trimmed)) {
      const itemsOrd: string[] = []
      while (i < lineas.length) {
        const lt = lineas[i].trim()
        const mNum = lt.match(/^\d+\.\s+(.+)$/)
        if (!mNum) break
        itemsOrd.push(mNum[1].trim())
        i += 1
      }
      bloques.push({ tipo: 'list', ordenada: true, items: itemsOrd })
      continue
    }

    // Párrafo continuo
    const parLineas: string[] = [trimmed]
    i += 1
    while (i < lineas.length) {
      const lt = lineas[i].trim()
      if (
        !lt ||
        /^#{1,3}\s+/.test(lt) ||
        /^(\*|-)\s+/.test(lt) ||
        /^\d+\.\s+/.test(lt) ||
        esLineaTabla(lt)
      ) {
        break
      }
      parLineas.push(lt)
      i += 1
    }
    bloques.push({ tipo: 'paragraph', texto: parLineas.join('\n') })
  }

  return bloques
}

function renderInlineReact(texto: string, keyPrefix: string): React.ReactNode[] {
  const regex = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*)/g
  const partes = texto.split(regex)
  return partes.map((parte, idx) => {
    const key = `${keyPrefix}-${idx}`
    if (parte.startsWith('**') && parte.endsWith('**') && parte.length > 4) {
      return (
        <strong key={key} className="font-bold text-slate-900">
          {parte.slice(2, -2)}
        </strong>
      )
    }
    if (parte.startsWith('`') && parte.endsWith('`') && parte.length > 2) {
      return (
        <code key={key} className="px-1 py-0.5 rounded bg-slate-100 text-uct-blue-primary font-mono text-[11px]">
          {parte.slice(1, -1)}
        </code>
      )
    }
    if (parte.startsWith('*') && parte.endsWith('*') && parte.length > 2) {
      return (
        <em key={key} className="italic text-slate-700">
          {parte.slice(1, -1)}
        </em>
      )
    }
    return <React.Fragment key={key}>{parte}</React.Fragment>
  })
}

function escaparHtml(texto: string): string {
  return texto
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inlineAHtmlSeguro(texto: string): string {
  const esc = escaparHtml(texto)
  return esc
    .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:#0f172a;">$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px;font-family:monospace;">$1</code>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
}

export function markdownAHtmlSeguro(contenido: string): string {
  const bloques = parsearBloquesMarkdown(contenido || '')
  return bloques
    .map((b) => {
      if (b.tipo === 'heading') {
        const size = b.nivel === 1 ? '15px' : b.nivel === 2 ? '14px' : '13px'
        return `<div style="font-weight:700;font-size:${size};color:#003865;margin:8px 0 4px;">${inlineAHtmlSeguro(b.texto)}</div>`
      }
      if (b.tipo === 'kpi_grid') {
        const rows = b.items
          .map(
            (it) =>
              `<div style="display:flex;justify-content:space-between;gap:12px;padding:6px 10px;border-bottom:1px solid #e2e8f0;font-size:12px;">
                <span style="color:#475569;font-weight:500;">${escaparHtml(it.etiqueta)}</span>
                <span style="color:#003865;font-weight:700;text-align:right;">${inlineAHtmlSeguro(it.valor)}</span>
              </div>`
          )
          .join('')
        return `<div style="border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;margin:6px 0;overflow:hidden;">${rows}</div>`
      }
      if (b.tipo === 'list') {
        const tag = b.ordenada ? 'ol' : 'ul'
        const itemsHtml = b.items.map((it) => `<li style="margin:3px 0;">${inlineAHtmlSeguro(it)}</li>`).join('')
        return `<${tag} style="margin:6px 0;padding-left:18px;font-size:12px;color:#1e293b;">${itemsHtml}</${tag}>`
      }
      if (b.tipo === 'table') {
        const ths = b.encabezados
          .map((h) => `<th style="padding:6px 8px;text-align:left;background:#003865;color:#fff;font-size:11px;">${inlineAHtmlSeguro(h)}</th>`)
          .join('')
        const trs = b.filas
          .map(
            (fila) =>
              `<tr>${fila
                .map((c) => `<td style="padding:5px 8px;border-top:1px solid #e2e8f0;font-size:11px;">${inlineAHtmlSeguro(c)}</td>`)
                .join('')}</tr>`
          )
          .join('')
        return `<table style="width:100%;border-collapse:collapse;border:1px solid #cbd5e1;margin:6px 0;"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`
      }
      return `<p style="margin:4px 0;line-height:1.5;font-size:12px;color:#1e293b;">${inlineAHtmlSeguro(b.texto).replace(/\n/g, '<br/>')}</p>`
    })
    .join('')
}

interface MarkdownRespuestaIAProps {
  contenido: string
  className?: string
}

export const MarkdownRespuestaIA: React.FC<MarkdownRespuestaIAProps> = ({ contenido, className = '' }) => {
  const bloques = parsearBloquesMarkdown(contenido || '')

  if (bloques.length === 0) {
    return null
  }

  return (
    <div className={`space-y-2.5 text-xs text-slate-800 leading-relaxed ${className}`}>
      {bloques.map((bloque, idx) => {
        if (bloque.tipo === 'heading') {
          const clasesNivel =
            bloque.nivel === 1
              ? 'text-sm font-bold text-uct-blue-primary pt-1'
              : bloque.nivel === 2
              ? 'text-[13px] font-bold text-uct-blue-primary pt-0.5'
              : 'text-xs font-bold text-slate-900 pt-0.5'
          return (
            <h4 key={idx} className={clasesNivel}>
              {renderInlineReact(bloque.texto, `h-${idx}`)}
            </h4>
          )
        }

        if (bloque.tipo === 'kpi_grid') {
          return (
            <div
              key={idx}
              className="rounded-xl border border-slate-200 bg-slate-50/80 divide-y divide-slate-200/70 overflow-hidden"
            >
              {bloque.items.map((item, kIdx) => (
                <div
                  key={kIdx}
                  className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 px-3 py-2 text-xs hover:bg-white/70 transition-colors"
                >
                  <span className="text-slate-600 font-medium">{item.etiqueta}</span>
                  <span className="font-bold text-uct-blue-primary text-right">
                    {renderInlineReact(item.valor, `kpi-${idx}-${kIdx}`)}
                  </span>
                </div>
              ))}
            </div>
          )
        }

        if (bloque.tipo === 'list') {
          const Tag = bloque.ordenada ? 'ol' : 'ul'
          const listStyle = bloque.ordenada ? 'list-decimal' : 'list-disc'
          return (
            <Tag key={idx} className={`${listStyle} pl-4 space-y-1 text-slate-800`}>
              {bloque.items.map((it, lIdx) => (
                <li key={lIdx} className="leading-relaxed">
                  {renderInlineReact(it, `li-${idx}-${lIdx}`)}
                </li>
              ))}
            </Tag>
          )
        }

        if (bloque.tipo === 'table') {
          return (
            <div key={idx} className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table className="w-full text-[11px] text-left border-collapse">
                <thead className="bg-uct-blue-primary text-white">
                  <tr>
                    {bloque.encabezados.map((enc, eIdx) => (
                      <th key={eIdx} className="px-2.5 py-1.5 font-semibold">
                        {renderInlineReact(enc, `th-${idx}-${eIdx}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {bloque.filas.map((fila, fIdx) => (
                    <tr key={fIdx} className="hover:bg-slate-50">
                      {fila.map((celda, cIdx) => (
                        <td key={cIdx} className="px-2.5 py-1.5 text-slate-700">
                          {renderInlineReact(celda, `td-${idx}-${fIdx}-${cIdx}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }

        const sublineas = bloque.texto.split('\n')
        return (
          <p key={idx} className="text-slate-800 leading-relaxed">
            {sublineas.map((sl, sIdx) => (
              <React.Fragment key={sIdx}>
                {renderInlineReact(sl, `p-${idx}-${sIdx}`)}
                {sIdx < sublineas.length - 1 && <br />}
              </React.Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}
