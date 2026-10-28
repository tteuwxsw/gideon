export const apiFetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('X-Gideon-CSRF', '1')
  }

  return fetch(input, { ...init, headers, credentials: 'same-origin' })
}

export const apiError = async (response: Response) => {
  try {
    const data = await response.json()
    return data.detail || data.mensagem || `Falha na solicita??o (${response.status}).`
  } catch {
    return `Falha na solicita??o (${response.status}).`
  }
}

export const messageId = () => {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export const formatTimestamp = (timestamp: string) => {
  const date = new Date(timestamp.includes('T') ? timestamp : timestamp.replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
