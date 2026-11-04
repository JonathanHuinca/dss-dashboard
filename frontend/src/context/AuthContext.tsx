import React, { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'
import { api } from '../api/client'

interface UserRole {
  id: number
  nombre: string
  descripcion?: string
}

export interface UserProfile {
  id: number
  email: string
  nombre_completo: string
  is_active: boolean
  roles: UserRole[]
}

interface DecodedToken {
  sub?: string
  user_id?: number
  rol?: string
  roles?: string[]
  allowed_datasets?: string[]
  can_use_ai?: boolean
  can_export?: boolean
  can_ingest?: boolean
  espacio_id?: number
  exp?: number
}

interface AuthContextType {
  token: string | null
  userRole: string | null
  roles: string[]
  userId: number | null
  allowedDatasets: string[]
  currentEspacioId: number
  setCurrentEspacioId: (id: number) => void
  hasDatasetAccess: (dataset: string) => boolean
  isAuthenticated: boolean
  isSuperAdmin: boolean
  isDirectivo: boolean
  isAnalista: boolean
  isGuardia: boolean
  canAccessAdmin: boolean
  canUseAi: boolean
  canExport: boolean
  canIngest: boolean
  login: (token: string) => void
  logout: () => void
  loginWithCredentials: (email: string, password: string) => Promise<boolean>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const TOKEN_KEY = 'uct_auth_token'

function parseJwt(token: string): DecodedToken | null {
  try {
    const base64Url = token.split('.')[1]
    if (!base64Url) return null
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload)
  } catch {
    return null
  }
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [userRole, setUserRole] = useState<string | null>(null)
  const [roles, setRoles] = useState<string[]>([])
  const [userId, setUserId] = useState<number | null>(null)
  const [allowedDatasets, setAllowedDatasets] = useState<string[]>(['biblioteca', 'estacionamiento'])
  const [currentEspacioId, setCurrentEspacioId] = useState<number>(1)
  const [canUseAi, setCanUseAi] = useState<boolean>(false)
  const [canExport, setCanExport] = useState<boolean>(false)
  const [canIngest, setCanIngest] = useState<boolean>(false)

  useEffect(() => {
    api.defaults.headers.common['X-Espacio-Id'] = currentEspacioId.toString()
  }, [currentEspacioId])

  const expireTimerRef = React.useRef<number | null>(null)

  const logout = () => {
    if (expireTimerRef.current) {
      clearTimeout(expireTimerRef.current)
      expireTimerRef.current = null
    }
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUserRole(null)
    setRoles([])
    setUserId(null)
    setAllowedDatasets(['biblioteca', 'estacionamiento'])
    setCanUseAi(false)
    setCanExport(false)
    setCanIngest(false)
  }

  const processToken = (jwtToken: string | null) => {
    if (expireTimerRef.current) {
      clearTimeout(expireTimerRef.current)
      expireTimerRef.current = null
    }

    if (!jwtToken) {
      logout()
      return
    }

    const decoded = parseJwt(jwtToken)
    if (!decoded || (decoded.exp && decoded.exp * 1000 <= Date.now())) {
      logout()
      return
    }

    const primaryRole = decoded.rol || (decoded.roles && decoded.roles[0]) || null
    const allRoles = decoded.roles || (decoded.rol ? [decoded.rol] : [])
    const uid = decoded.user_id ? Number(decoded.user_id) : (decoded.sub ? Number(decoded.sub) : null)
    const datasets = decoded.allowed_datasets || ['biblioteca', 'estacionamiento']

    setUserRole(primaryRole)
    setRoles(allRoles)
    setUserId(uid)
    setAllowedDatasets(datasets)
    setCanUseAi(Boolean(decoded.can_use_ai))
    setCanExport(Boolean(decoded.can_export))
    setCanIngest(Boolean(decoded.can_ingest))

    // Configurar temporizador exacto para el instante de expiración del token
    if (decoded.exp) {
      const msRestantes = Math.max(0, decoded.exp * 1000 - Date.now())
      expireTimerRef.current = window.setTimeout(() => {
        logout()
      }, msRestantes)
    }
  }

  useEffect(() => {
    processToken(token)
    return () => {
      if (expireTimerRef.current) {
        clearTimeout(expireTimerRef.current)
      }
    }
  }, [token])

  // Escuchar evento global de expiración 401 disparado por interceptores
  useEffect(() => {
    const handleAuthExpired = () => {
      logout()
    }
    window.addEventListener('uct:auth-expired', handleAuthExpired)
    return () => window.removeEventListener('uct:auth-expired', handleAuthExpired)
  }, [])

  // Verificación periódica cada 3 segundos como red de seguridad
  useEffect(() => {
    if (!token) return
    const interval = setInterval(() => {
      const decoded = parseJwt(token)
      if (decoded?.exp && decoded.exp * 1000 <= Date.now()) {
        logout()
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [token])

  useEffect(() => {
    const interceptor = api.interceptors.request.use((config) => {
      const currentToken = localStorage.getItem(TOKEN_KEY)
      if (currentToken && config.headers) {
        config.headers.Authorization = `Bearer ${currentToken}`
      }
      return config
    })
    return () => {
      api.interceptors.request.eject(interceptor)
    }
  }, [])

  const login = (newToken: string) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
    processToken(newToken)
  }

  const loginWithCredentials = async (email: string, password: string): Promise<boolean> => {
    try {
      const res = await api.post('/auth/login', { email, password })
      if (res.data?.access_token) {
        login(res.data.access_token)
        return true
      }
      return false
    } catch {
      return false
    }
  }

  const isAuthenticated = Boolean(token && userRole)
  const isSuperAdmin =
    roles.includes('SuperAdmin') ||
    roles.includes('Admin_Sistema') ||
    userRole === 'SuperAdmin' ||
    userRole === 'Admin_Sistema'
  const isDirectivo =
    roles.includes('Directivo') ||
    roles.includes('Director_Recinto') ||
    userRole === 'Directivo' ||
    userRole === 'Director_Recinto'
  const isAnalista =
    roles.includes('Analista_Consulta') ||
    userRole === 'Analista_Consulta'
  const isGuardia =
    roles.includes('Guardia_Seguridad') ||
    userRole === 'Guardia_Seguridad'
  const canAccessAdmin = isSuperAdmin || isDirectivo

  const hasDatasetAccess = (dataset: string): boolean => {
    if (isSuperAdmin) return true
    return allowedDatasets.includes(dataset)
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        userRole,
        roles,
        userId,
        allowedDatasets,
        currentEspacioId,
        setCurrentEspacioId,
        hasDatasetAccess,
        isAuthenticated,
        isSuperAdmin,
        isDirectivo,
        isAnalista,
        isGuardia,
        canAccessAdmin,
        canUseAi: isSuperAdmin ? true : canUseAi,
        canExport: isSuperAdmin ? true : canExport,
        canIngest: isSuperAdmin ? true : canIngest,
        login,
        logout,
        loginWithCredentials,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
