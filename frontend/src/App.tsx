import React, { useState, useEffect, useRef } from 'react'
import { HolographicOrb } from './components/HolographicOrb'
import { ChatTimeline } from './components/ChatTimeline'
import { ChatInput } from './components/ChatInput'
import { VoiceStatus } from './components/VoiceStatus'
import { SettingsSheet } from './components/SettingsSheet'
import { ActivityDrawer } from './components/ActivityDrawer'
import { Settings, Activity, ShieldAlert, WifiOff } from 'lucide-react'
import type { Message, ModoEscuta } from './types'
import { apiError, apiFetch, messageId } from './api'

type ChatPhase = 'idle' | 'pending' | 'streaming'

export const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([])
  const [audioLevel, setAudioLevel] = useState(0)
  const [isThinking, setIsThinking] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [chatPhase, setChatPhase] = useState<ChatPhase>('idle')
  const [isListening, setIsListening] = useState(true)
  const [currentLanguage, setCurrentLanguage] = useState('pt-BR')
  const [voiceMode, setVoiceMode] = useState<ModoEscuta>('ativacao_por_nome')
  const [voiceInterruptionEnabled, setVoiceInterruptionEnabled] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [authReady, setAuthReady] = useState(false)
  const [authError, setAuthError] = useState('')
  const [connection, setConnection] = useState<'connecting' | 'online' | 'offline'>('connecting')
  const [emergencyStopped, setEmergencyStopped] = useState(false)
  const [vigilanteAlert, setVigilanteAlert] = useState<{ mensagem: string; nivel: string } | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const authStartedRef = useRef(false)
  const reconnectTimerRef = useRef<number | undefined>(undefined)
  const chatAbortRef = useRef<AbortController | null>(null)
  const chatBusyRef = useRef(false)

  useEffect(() => {
    if (authStartedRef.current) return
    authStartedRef.current = true
    const authenticate = async () => {
      try {
        const params = new URLSearchParams(window.location.hash.slice(1))
        const token = params.get('token')

        if (token) {
          const login = await apiFetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
          })
          window.history.replaceState(null, '', window.location.pathname + window.location.search)
          if (!login.ok) {
            const existingSession = await apiFetch('/api/status')
            if (!existingSession.ok) throw new Error('Nao foi possivel autenticar esta janela.')
          }
        }

        const statusResponse = await apiFetch('/api/status')
        if (!statusResponse.ok) throw new Error('Abra a Gideon pelo atalho do aplicativo.')
        const status = await statusResponse.json()
        const [languageResponse, voiceResponse, geminiResponse] = await Promise.all([
          apiFetch('/api/idioma'),
          apiFetch('/api/voz/status'),
          apiFetch('/api/gemini/status')
        ])

        setEmergencyStopped(Boolean(status.parada_emergencia))
        if (languageResponse.ok) {
          const language = await languageResponse.json()
          if (language.idioma) setCurrentLanguage(language.idioma)
        }
        if (voiceResponse.ok) {
          const voice = await voiceResponse.json()
          if (voice.modo_escuta) setVoiceMode(voice.modo_escuta)
          if (typeof voice.barge_in_ativo === 'boolean') setVoiceInterruptionEnabled(voice.barge_in_ativo)
          setIsListening(Boolean(voice.ativa ?? voice.ativo ?? voice.escuta_ativa ?? voice.rodando))
        }
        if (geminiResponse.ok) {
          const gemini = await geminiResponse.json()
          if (!gemini.configurada) {
            setVigilanteAlert({
              mensagem: 'Conecte sua chave do Gemini em Configurações para habilitar respostas de IA.',
              nivel: 'info'
            })
          }
        }
        setAuthReady(true)
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : 'Falha ao iniciar a interface.')
        setConnection('offline')
      }
    }

    void authenticate()
  }, [])

  useEffect(() => {
    if (!authReady) return
    let disposed = false
    let lastSequence = 0

    const applyState = (state: string) => {
      setIsThinking(['thinking', 'executing', 'observing'].includes(state))
      setIsSpeaking(state === 'speaking')
      if (state === 'listening') setIsListening(true)
    }

    const connectWs = () => {
      if (disposed) return
      setConnection('connecting')
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        setConnection('online')
        ws.send(JSON.stringify({ tipo: 'pronto', cliente: 'react-app' }))
      }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.sequencia && data.sequencia <= lastSequence) return
          if (data.sequencia) lastSequence = data.sequencia

          if (data.tipo === 'status' && data.estado_interface) {
            lastSequence = data.estado_interface.sequencia || lastSequence
            applyState(data.estado_interface.estado || 'idle')
          } else if (data.tipo === 'estado_ia') {
            applyState(data.estado)
          } else if (data.tipo === 'voz_nivel') {
            setAudioLevel(Math.max(0, Math.min(1, Number(data.nivel) || 0)))
          } else if (data.tipo === 'pensando') {
            setIsThinking(Boolean(data.ativo))
          } else if (data.tipo === 'fala_inicio') {
            setIsSpeaking(true)
          } else if (data.tipo === 'fala_fim') {
            setIsSpeaking(false)
          } else if (data.tipo === 'ouvindo') {
            setIsListening(Boolean(data.ativo))
          } else if (data.tipo === 'idioma_alterado') {
            setCurrentLanguage(data.idioma)
          } else if (data.tipo === 'transcricao_voz' && data.texto) {
            setMessages((current) => [
              ...current,
              { id: messageId(), role: 'user', content: data.texto, timestamp: new Date().toISOString() }
            ])
          } else if (data.tipo === 'resposta_voz' && data.texto) {
            setMessages((current) => [
              ...current,
              { id: messageId(), role: 'assistant', content: data.texto, timestamp: new Date().toISOString() }
            ])
          } else if (data.tipo === 'parada_emergencia') {
            setEmergencyStopped(Boolean(data.ativa))
            setVigilanteAlert({
              mensagem: data.ativa
                ? 'Parada de emergencia ativada. As ferramentas locais estao bloqueadas.'
                : 'Ferramentas locais liberadas novamente.',
              nivel: data.ativa ? 'danger' : 'success'
            })
          } else if (data.tipo === 'som') {
            new Audio(`/api/sons/${data.som}`).play().catch(() => {})
          } else if (data.tipo === 'alerta_vigilante') {
            setVigilanteAlert({ mensagem: data.mensagem, nivel: data.nivel || 'info' })
            window.setTimeout(() => setVigilanteAlert(null), 8000)
          }
        } catch {
          // Um evento invalido nao deve interromper o canal em tempo real.
        }
      }

      ws.onclose = () => {
        if (disposed) return
        setConnection('offline')
        reconnectTimerRef.current = window.setTimeout(connectWs, 1800)
        setAudioLevel(0)
      }
    }

    connectWs()
    return () => {
      disposed = true
      window.clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [authReady])

  const handleSendMessage = async (texto: string) => {
    if (chatBusyRef.current) return
    chatBusyRef.current = true
    setChatPhase('pending')
    const controller = new AbortController()
    chatAbortRef.current = controller
    const userMsgId = messageId()
    const assistantMsgId = messageId()

    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: texto,
        timestamp: new Date().toISOString()
      },
      {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
        status: 'pending'
      }
    ])

    try {
      const response = await apiFetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensagem: texto }),
        signal: controller.signal
      })

      if (!response.ok || !response.body) throw new Error(await apiError(response))

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let accumulatedText = ''
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''
        if (done && buffer.trim()) {
          blocks.push(buffer)
          buffer = ''
        }

        for (const block of blocks) {
          const line = block.split('\n').find((item) => item.startsWith('data:')) || ''
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))
              if (event.tipo === 'chunk') {
                setChatPhase('streaming')
                accumulatedText += event.texto || ''
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: accumulatedText, isStreaming: true, status: 'streaming' }
                      : m
                  )
                )
              } else if (event.tipo === 'fim') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? {
                          ...m,
                          content: accumulatedText,
                          isStreaming: false,
                          model: event.modelo,
                          status: 'complete',
                          tokens: event.total_tokens,
                          latencyMs: event.latencia_ms
                        }
                      : m
                  )
                )
              } else if (event.tipo === 'erro') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? {
                          ...m,
                          content: event.mensagem || 'Ocorreu um erro no processamento.',
                          isStreaming: false,
                          status: 'error'
                        }
                      : m
                  )
                )
              }
            } catch {
              // json parse
            }
          }
        }
        if (done) break
      }
    } catch (error) {
      const cancelled = error instanceof DOMException && error.name === 'AbortError'
      if (cancelled) {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMsgId
              ? { ...message, content: message.content || 'Resposta interrompida.', isStreaming: false, status: 'cancelled' }
              : message
          )
        )
        return
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: 'Falha na comunicação com o servidor.', isStreaming: false }
            : m
        )
      )
    } finally {
      chatBusyRef.current = false
      chatAbortRef.current = null
      setChatPhase('idle')
    }
  }

  const stopResponse = () => chatAbortRef.current?.abort()

  const toggleVoice = async () => {
    try {
      const nextListening = !isListening
      const response = await apiFetch(nextListening ? '/api/voz/iniciar' : '/api/voz/parar', {
        method: 'POST'
      })
      if (!response.ok) throw new Error(await apiError(response))
      setIsListening(nextListening)
    } catch (error) {
      setVigilanteAlert({
        mensagem: error instanceof Error ? error.message : 'Nao foi possivel alterar a escuta.',
        nivel: 'danger'
      })
    }
  }

  const chatBusy = chatPhase !== 'idle'
  const interfaceThinking = isThinking || chatBusy

  if (authError) {
    return (
      <main className="auth-screen">
        <div className="auth-card" role="alert">
          <WifiOff aria-hidden="true" />
          <p className="eyebrow">Conexao local necessaria</p>
          <h1>Nao foi possivel abrir a Gideon</h1>
          <p>{authError}</p>
        </div>
      </main>
    )
  }

  return (
    <div className="app-shell">
      <div className="ambient-grid" aria-hidden="true" />
      <header className="app-header">
        <div className="flex items-center gap-3">
          <div className={`connection-dot ${connection}`} aria-hidden="true" />
          <h1 className="brand-name">
            Gideon <span className="brand-version">Núcleo local · v0.4.6</span>
          </h1>
        </div>

        <VoiceStatus
          isSpeaking={isSpeaking}
          isListening={isListening}
          isThinking={interfaceThinking}
          connection={connection}
          audioLevel={audioLevel}
          mode={voiceMode}
          onToggleMute={async () => {
            const response = await apiFetch('/api/voz/interromper', { method: 'POST' })
            if (!response.ok) setVigilanteAlert({ mensagem: await apiError(response), nivel: 'danger' })
          }}
        />

        <nav className="header-actions" aria-label="Paineis da Gideon">
          <button
            onClick={() => {
              setSettingsOpen(false)
              setActivityOpen(true)
            }}
            aria-label="Abrir atividades"
            className="icon-button"
            title="Atividade e auditoria"
          >
            <Activity className="w-4 h-4" />
          </button>
          <button
            onClick={() => {
              setActivityOpen(false)
              setSettingsOpen(true)
            }}
            className="icon-button"
            title="Configurações"
            aria-label="Abrir configuracoes"
          >
            <Settings className="w-4 h-4" />
          </button>
        </nav>
      </header>

      {emergencyStopped && (
        <div className="emergency-bar" role="status">
          <ShieldAlert aria-hidden="true" />
          <span>Protecao ativa: ferramentas locais pausadas</span>
          <button onClick={() => setSettingsOpen(true)}>Revisar</button>
        </div>
      )}

      <main className="app-main">
        {vigilanteAlert && (
          <div className={`app-notice ${vigilanteAlert.nivel}`} role="status" aria-live="polite">
            <div className="notice-pulse" aria-hidden="true" />
            <p className="notice-message">
              {vigilanteAlert.mensagem}
            </p>
            <button
              onClick={() => setVigilanteAlert(null)}
              className="notice-close"
              aria-label="Fechar aviso"
            >
              ✕
            </button>
          </div>
        )}
        {messages.length === 0 ? (
          <section className="welcome-stage" aria-label="Inicio">
            <HolographicOrb
              audioLevel={audioLevel}
              isThinking={interfaceThinking}
              isSpeaking={isSpeaking}
              isListening={isListening}
              compact={false}
              onClick={toggleVoice}
            />
            <ChatTimeline
              messages={messages}
              isThinking={chatPhase === 'pending'}
              onSelectSuggestion={handleSendMessage}
            />
          </section>
        ) : (
          <>
            <div className="presence-rail">
              <HolographicOrb
                audioLevel={audioLevel}
                isThinking={interfaceThinking}
                isSpeaking={isSpeaking}
                isListening={isListening}
                compact={true}
                onClick={toggleVoice}
              />
            </div>
            <ChatTimeline
              messages={messages}
              isThinking={chatPhase === 'pending'}
              onSelectSuggestion={handleSendMessage}
            />
          </>
        )}

        <ChatInput
          onSendMessage={handleSendMessage}
          disabled={!authReady}
          isGenerating={chatBusy}
          onStop={stopResponse}
          isListening={isListening}
          onToggleVoice={toggleVoice}
        />
      </main>

      <SettingsSheet
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        currentLanguage={currentLanguage}
        onChangeLanguage={async (novo) => {
          const response = await apiFetch('/api/idioma', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ idioma: novo })
          })
          if (!response.ok) throw new Error(await apiError(response))
          setCurrentLanguage(novo)
        }}
        currentVoiceMode={voiceMode}
        onChangeVoiceMode={async (novoModo) => {
          const response = await apiFetch('/api/voz/configurar', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ modo_escuta: novoModo })
          })
          if (!response.ok) throw new Error(await apiError(response))
          setVoiceMode(novoModo)
        }}
        voiceInterruptionEnabled={voiceInterruptionEnabled}
        onChangeVoiceInterruption={async (ativa) => {
          const response = await apiFetch('/api/voz/configurar', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ barge_in_ativo: ativa })
          })
          if (!response.ok) throw new Error(await apiError(response))
          setVoiceInterruptionEnabled(ativa)
        }}
        onEmergencyStop={async () => {
          const response = await apiFetch('/api/emergencia/parar', { method: 'POST' })
          if (!response.ok) throw new Error(await apiError(response))
          setEmergencyStopped(true)
        }}
        onEmergencyResume={async () => {
          const response = await apiFetch('/api/emergencia/retomar', { method: 'POST' })
          if (!response.ok) throw new Error(await apiError(response))
          setEmergencyStopped(false)
        }}
        onClearChat={async () => {
          const response = await apiFetch('/api/chat/limpar', { method: 'POST' })
          if (!response.ok) throw new Error(await apiError(response))
          setMessages([])
          setSettingsOpen(false)
        }}
      />

      <ActivityDrawer
        isOpen={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
    </div>
  )
}
export default App
