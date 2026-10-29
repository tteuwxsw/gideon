import React, { useState, useEffect } from 'react'
import { useRef } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { X, Globe, Radio, AlertOctagon, RefreshCw, Trash2, Check, KeyRound, Volume2 } from 'lucide-react'
import type { IdiomaOpcao, ModoEscuta } from '../types'
import { apiError, apiFetch } from '../api'

interface SettingsSheetProps {
  isOpen: boolean
  onClose: () => void
  currentLanguage: string
  onChangeLanguage: (idioma: string) => Promise<void>
  currentVoiceMode: ModoEscuta
  onChangeVoiceMode: (modo: ModoEscuta) => Promise<void>
  voiceInterruptionEnabled: boolean
  onChangeVoiceInterruption: (ativa: boolean) => Promise<void>
  interfaceSoundsEnabled: boolean
  interfaceSoundsVolume: number
  onChangeInterfaceSounds: (ativa: boolean, volume: number) => Promise<void>
  onEmergencyStop: () => Promise<void>
  onEmergencyResume: () => Promise<void>
  onClearChat: () => Promise<void>
}

export const SettingsSheet: React.FC<SettingsSheetProps> = ({
  isOpen,
  onClose,
  currentLanguage,
  onChangeLanguage,
  currentVoiceMode,
  onChangeVoiceMode,
  voiceInterruptionEnabled,
  onChangeVoiceInterruption,
  interfaceSoundsEnabled,
  interfaceSoundsVolume,
  onChangeInterfaceSounds,
  onEmergencyStop,
  onEmergencyResume,
  onClearChat
}) => {
  const [, setLanguages] = useState<IdiomaOpcao[]>([])
  const [savingLang, setSavingLang] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [geminiConfigured, setGeminiConfigured] = useState(false)
  const [geminiKey, setGeminiKey] = useState('')
  const [savingGemini, setSavingGemini] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  const noticeTimerRef = useRef<number | undefined>(undefined)
  const reduceMotion = useReducedMotion()
  const isMobile = window.matchMedia('(max-width: 760px)').matches
  useEffect(() => {
    closeRef.current = onClose
  }, [onClose])


  useEffect(() => {
    if (isOpen) {
      Promise.all([apiFetch('/api/idioma'), apiFetch('/api/gemini/status')])
        .then(async ([languageResponse, geminiResponse]) => {
          if (languageResponse.ok) {
            const data = await languageResponse.json()
            if (data.idiomas) setLanguages(data.idiomas)
          }
          if (geminiResponse.ok) {
            const data = await geminiResponse.json()
            setGeminiConfigured(Boolean(data.configurada))
          }
        }).catch(() => {})
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const previousFocus = document.activeElement as HTMLElement | null
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeRef.current()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
        )
      )
      const first = focusable[0]
      const last = focusable.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    window.requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>('button')?.focus())

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      previousFocus?.focus()
    }
  }, [isOpen])

  const notify = (msg: string) => {
    setNotice(msg)
    window.clearTimeout(noticeTimerRef.current)
    noticeTimerRef.current = window.setTimeout(() => setNotice(null), 3000)
  }

  const runAction = async (action: () => Promise<void>, successMessage: string) => {
    try {
      await action()
      notify(successMessage)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Nao foi possivel concluir a alteracao.')
    }
  }

  const handleLang = async (cod: string) => {
    setSavingLang(true)
    try {
      await onChangeLanguage(cod)
      notify('Idioma atualizado com sucesso.')
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Nao foi possivel alterar o idioma.')
    }
    setSavingLang(false)
  }

  const saveGeminiKey = async () => {
    if (!geminiKey.trim()) return
    setSavingGemini(true)
    try {
      const response = await apiFetch('/api/gemini/chave', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chave: geminiKey.trim() })
      })
      if (!response.ok) throw new Error(await apiError(response))
      setGeminiConfigured(true)
      setGeminiKey('')
      notify('Gemini conectado e chave guardada no cofre do sistema.')
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Não foi possível validar a chave do Gemini.')
    } finally {
      setSavingGemini(false)
    }
  }

  useEffect(() => () => window.clearTimeout(noticeTimerRef.current), [])

  const panelInitial = reduceMotion
    ? { opacity: 0 }
    : isMobile ? { opacity: 0, y: '100%' } : { opacity: 0, scale: 0.97, y: 12 }


  return (

    <AnimatePresence>
      {isOpen && (
        <div className="settings-layer">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.16 }}
            className="sheet-backdrop"
            onClick={() => closeRef.current()}
          />

          <motion.div
            initial={panelInitial}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            ref={dialogRef}
            exit={reduceMotion ? { opacity: 0 } : isMobile ? { opacity: 0, y: '100%' } : { opacity: 0, scale: 0.98, y: 8 }}
            transition={{ type: 'spring', damping: 34, stiffness: 380, mass: 0.8 }}
            className="settings-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Configuracoes da Gideon"
            tabIndex={-1}
          >
            <div className="sheet-header">
              <h3 className="text-lg font-medium text-slate-100">Configurações da Gideon</h3>
              <button
                onClick={() => closeRef.current()}
                className="sheet-close"
                aria-label="Fechar configuracoes"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {notice && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                role="status"
                aria-live="polite"
                className="settings-notice"
              >
                {notice}
              </motion.div>
            )}

            <div className="settings-content">
              {/* Idioma Selector */}
              <div>
                <label className="setting-label">
                  <Globe className="w-4 h-4" />
                  <span>Idioma da Gideon</span>
                </label>
                <div className="setting-grid" role="group" aria-label="Idioma da Gideon">
                  {[
                    { cod: 'pt-BR', label: 'Português', sub: 'Brasil' },
                    { cod: 'en-US', label: 'English', sub: 'US' },
                    { cod: 'es-ES', label: 'Español', sub: 'España' }
                  ].map((item) => (
                    <button
                      key={item.cod}
                      type="button"
                      aria-pressed={currentLanguage === item.cod}
                      onClick={() => handleLang(item.cod)}
                      disabled={savingLang}
                      className={`setting-option ${currentLanguage === item.cod ? 'selected' : ''}`}
                    >
                      <div className="font-medium text-xs flex items-center justify-between">
                        <span>{item.label}</span>
                        {currentLanguage === item.cod && <Check className="w-3.5 h-3.5" />}
                      </div>
                      <div className="text-[10px] text-slate-400">{item.sub}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Modo de Escuta */}
              <div>
                <label className="setting-label">
                  <Radio className="w-4 h-4" />
                  <span>Modo de Escuta Inteligente</span>
                </label>
                <div className="setting-grid" role="group" aria-label="Modo de escuta">
                  {[
                    { mode: 'ativacao_por_nome', label: 'Por Nome', desc: '"Gideon"' },
                    { mode: 'conversa_continua', label: 'Contínua', desc: 'Até silêncio' },
                    { mode: 'conversa_livre', label: 'Livre', desc: 'Mãos livres' }
                  ].map((m) => (
                    <button
                      key={m.mode}
                      type="button"
                      aria-pressed={currentVoiceMode === m.mode}
                      onClick={() => runAction(
                        () => onChangeVoiceMode(m.mode as ModoEscuta),
                        'Modo de escuta atualizado.'
                      )}
                      className={`setting-option ${currentVoiceMode === m.mode ? 'selected' : ''}`}
                    >
                      <div className="font-medium text-xs">{m.label}</div>
                      <div className="text-[10px] text-slate-400">{m.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="setting-label" htmlFor="interface-sound-volume">
                  <Volume2 className="w-4 h-4" />
                  <span>Sons da interface</span>
                </label>
                <div className="setting-grid" role="group" aria-label="Sons da interface">
                  {[true, false].map((ativa) => (
                    <button
                      key={String(ativa)}
                      type="button"
                      aria-pressed={interfaceSoundsEnabled === ativa}
                      onClick={() => runAction(
                        () => onChangeInterfaceSounds(ativa, interfaceSoundsVolume),
                        `Sons da interface ${ativa ? 'ativados' : 'desativados'}.`
                      )}
                      className={`setting-option ${interfaceSoundsEnabled === ativa ? 'selected' : ''}`}
                    >
                      <div className="font-medium text-xs">{ativa ? 'Ativados' : 'Desativados'}</div>
                    </button>
                  ))}
                </div>
                <div className="sound-volume-row">
                  <input
                    id="interface-sound-volume"
                    type="range"
                    min="0"
                    max="0.5"
                    step="0.05"
                    value={interfaceSoundsVolume}
                    disabled={!interfaceSoundsEnabled}
                    onChange={(event) => {
                      const volume = Number(event.target.value)
                      void runAction(
                        () => onChangeInterfaceSounds(true, volume),
                        `Volume dos sons em ${Math.round(volume * 100)}%.`
                      )
                    }}
                    aria-label="Volume dos sons da interface"
                  />
                  <span>{Math.round(interfaceSoundsVolume * 100)}%</span>
                </div>
              </div>

              <div>
                <label className="setting-label">
                  <Radio className="w-4 h-4" />
                  <span>Interromper ao dizer “Gideon”</span>
                </label>
                <p className="setting-help">
                  Durante a fala, somente a palavra de ativação interrompe a resposta.
                </p>
                <div className="setting-grid" role="group" aria-label="Interrupção da fala por voz">
                  {[true, false].map((ativa) => (
                    <button
                      key={String(ativa)}
                      type="button"
                      aria-pressed={voiceInterruptionEnabled === ativa}
                      onClick={() => runAction(
                        () => onChangeVoiceInterruption(ativa),
                        `Interrupção por voz ${ativa ? 'ativada' : 'desativada'}.`
                      )}
                      className={`setting-option ${voiceInterruptionEnabled === ativa ? 'selected' : ''}`}
                    >
                      <div className="font-medium text-xs">{ativa ? 'Ativada' : 'Desativada'}</div>
                      <div className="text-[10px] text-slate-400">{ativa ? 'Diga “Gideon”' : 'Não interromper'}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="setting-label" htmlFor="gemini-api-key">
                  <KeyRound className="w-4 h-4" />
                  <span>Google Gemini</span>
                  <span className={`integration-status ${geminiConfigured ? 'connected' : ''}`}>
                    {geminiConfigured ? 'Conectado' : 'Não configurado'}
                  </span>
                </label>
                <p className="setting-help">
                  A chave fica no cofre do sistema e nunca é gravada no código ou exibida novamente.
                </p>
                <div className="api-key-row">
                  <input
                    id="gemini-api-key"
                    type="password"
                    value={geminiKey}
                    onChange={(event) => setGeminiKey(event.target.value)}
                    placeholder={geminiConfigured ? 'Substituir chave atual' : 'Cole sua chave da API'}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button type="button" onClick={saveGeminiKey} disabled={!geminiKey.trim() || savingGemini}>
                    {savingGemini ? 'Validando…' : 'Salvar'}
                  </button>
                </div>
              </div>

              {/* Botões de Ação de Sistema */}
              <div className="system-actions">
                <button
                  onClick={async () => {
                    await onClearChat()
                    notify('Conversa reiniciada com sucesso.')
                  }}
                  className="system-action"
                >
                  <Trash2 className="w-4 h-4 text-slate-400" />
                  <span>Limpar conversa atual</span>
                </button>

                <div className="danger-actions">
                  <button
                    onClick={async () => {
                      await onEmergencyStop()
                      notify('Parada de emergência ativada.')
                    }}
                    className="system-action danger"
                  >
                    <AlertOctagon className="w-4 h-4 text-red-400" />
                    <span>Parada de Emergência</span>
                  </button>

                  <button
                    onClick={async () => {
                      await onEmergencyResume()
                      notify('Ferramentas liberadas novamente.')
                    }}
                    className="system-action positive"
                  >
                    <RefreshCw className="w-4 h-4 text-emerald-400" />
                    <span>Retomar Ferramentas</span>
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
