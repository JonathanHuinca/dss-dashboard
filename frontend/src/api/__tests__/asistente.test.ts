import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sendInteractiveChatStream } from '../asistente'

function crearStreamDesdeTextos(partes: string[], onRelease?: () => void) {
  const encoder = new TextEncoder()
  let idx = 0
  return {
    getReader: () => ({
      read: async () => {
        if (idx >= partes.length) return { done: true, value: undefined }
        const val = encoder.encode(partes[idx++])
        return { done: false, value: val }
      },
      releaseLock: () => {
        if (onRelease) onRelease()
      },
    }),
  }
}

describe('sendInteractiveChatStream SSE', () => {
  beforeEach(() => {
    localStorage.setItem('uct_auth_token', 'jwt-demo')
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('procesa frames meta, text y done liberando el reader al terminar', async () => {
    let lockLiberado = false
    const frames = [
      'data: {"type":"meta","intent":"consultar_mapa_calor","tipo":"component","component":"HeatmapChart","conversacion_id":"c1"}\n\n',
      'data: {"type":"text","chunk":"Hola "}\n\ndata: {"type":"text","chunk":"UCT"}\n\n',
      'data: {"type":"done"}\n\n',
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      body: crearStreamDesdeTextos(frames, () => {
        lockLiberado = true
      }),
    } as unknown as Response)

    const metas: any[] = []
    const chunks: string[] = []
    const onDone = vi.fn()
    const onError = vi.fn()

    await sendInteractiveChatStream(
      { prompt: 'Ver mapa', dataset_tipo: 'biblioteca', session_id: 's1' },
      {
        onMeta: m => metas.push(m),
        onChunk: c => chunks.push(c),
        onDone,
        onError,
      }
    )

    expect(metas[0]?.intent).toBe('consultar_mapa_calor')
    expect(chunks.join('')).toBe('Hola UCT')
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
    expect(lockLiberado).toBe(true)
  })

  it('dispara uct:auth-expired y limpia token ante HTTP 401', async () => {
    const expiredListener = vi.fn()
    window.addEventListener('uct:auth-expired', expiredListener)

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Sesión expirada' }),
    } as unknown as Response)

    const onError = vi.fn()
    await sendInteractiveChatStream(
      { prompt: 'Hola', dataset_tipo: 'biblioteca', session_id: 's1' },
      { onMeta: vi.fn(), onChunk: vi.fn(), onDone: vi.fn(), onError }
    )

    window.removeEventListener('uct:auth-expired', expiredListener)
    expect(expiredListener).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('uct_auth_token')).toBeNull()
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('no invoca onError cuando fetch se cancela vía AbortError', async () => {
    const abortErr = Object.assign(new Error('Aborted'), { name: 'AbortError' })
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(abortErr)

    const onError = vi.fn()
    const ac = new AbortController()
    await sendInteractiveChatStream(
      { prompt: 'Abortar', dataset_tipo: 'biblioteca', session_id: 's1' },
      { onMeta: vi.fn(), onChunk: vi.fn(), onDone: vi.fn(), onError },
      ac.signal
    )
    expect(onError).not.toHaveBeenCalled()
  })
})
