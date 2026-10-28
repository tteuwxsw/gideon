import React, { useState, useEffect } from 'react'
import { useRef } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { X, Globe, Radio, AlertOctagon, RefreshCw, Trash2, Check } from 'lucide-react'
import type { IdiomaOpcao, ModoEscuta } from '../types'

interface SettingsSheetProps {
  isOpen: boolean
  onClose: () => void
  currentLanguage: string
  onChangeLanguage: (idioma: string) => Promise<void>
  currentVoiceMode: ModoEscuta
  onChangeVoiceMode: (modo: ModoEscuta) => Promise<void>
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
  onEmergencyStop,
  onEmergencyResume,
  onClearChat
}) => {
  const [, setLanguages] = useState<IdiomaOpcao[]>([])
  const [savingLang, setSavingLang] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
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
      fetch('/api/idioma')
        .then((r) => r.json())
        .then((data) => {
          if (data.idiomas) setLanguages(data.idiomas)
        })
        .catch(() => {})
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
                className="mt-3 py-1.5 px-3 rounded-xl bg-cyan-500/20 text-cyan-300 text-xs text-center border border-cyan-500/30"
              >
                {notice}
              </motion.div>
            )}

            <div className="settings-content">
              {/* Idioma Selector */}
              <div>
                <label className="flex items-center gap-2 text-xs font-medium text-slate-300 mb-2">
                  <Globe className="w-4 h-4 text-cyan-400" />
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
                      className={`py-2 px-3 rounded-xl text-left border transition-all ${
                        currentLanguage === item.cod
                          ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200 shadow-[0_0_12px_rgba(0,243,255,0.25)]'
                          : 'border-white/10 hover:border-white/20 bg-white/5 text-slate-300'
                      }`}
                    >
                      <div className="font-medium text-xs flex items-center justify-between">
                        <span>{item.label}</span>
                        {currentLanguage === item.cod && <Check className="w-3.5 h-3.5 text-cyan-400" />}
                      </div>
                      <div className="text-[10px] text-slate-400">{item.sub}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Modo de Escuta */}
              <div>
                <label className="flex items-center gap-2 text-xs font-medium text-slate-300 mb-2">
                  <Radio className="w-4 h-4 text-cyan-400" />
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
                      className={`py-2 px-3 rounded-xl text-left border transition-all ${
                        currentVoiceMode === m.mode
                          ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200'
                          : 'border-white/10 hover:border-white/20 bg-white/5 text-slate-300'
                      }`}
                    >
                      <div className="font-medium text-xs">{m.label}</div>
                      <div className="text-[10px] text-slate-400">{m.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Botões de Ação de Sistema */}
              <div className="system-actions">
                <button
                  onClick={async () => {
                    await onClearChat()
                    notify('Conversa reiniciada com sucesso.')
                  }}
                  className="w-full py-2.5 px-4 rounded-xl text-xs font-medium bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 flex items-center justify-center gap-2 transition-colors"
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
                    className="py-2.5 px-3 rounded-xl text-xs font-medium bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30 flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <AlertOctagon className="w-4 h-4 text-red-400" />
                    <span>Parada de Emergência</span>
                  </button>

                  <button
                    onClick={async () => {
                      await onEmergencyResume()
                      notify('Ferramentas liberadas novamente.')
                    }}
                    className="py-2.5 px-3 rounded-xl text-xs font-medium bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 flex items-center justify-center gap-1.5 transition-colors"
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
