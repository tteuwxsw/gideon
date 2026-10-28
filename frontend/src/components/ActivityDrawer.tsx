import React, { useState, useEffect } from 'react'
import { useRef } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { X, Activity, CheckCircle, CircleAlert, Terminal } from 'lucide-react'
import type { ActivityItem } from '../types'
import { formatTimestamp } from '../api'

interface ActivityDrawerProps {
  isOpen: boolean
  onClose: () => void
}

export const ActivityDrawer: React.FC<ActivityDrawerProps> = ({ isOpen, onClose }) => {
const describeResult = (activity: ActivityItem) => {
  if (activity.mensagem_humana) return activity.mensagem_humana
  if (typeof activity.resultado === 'string') return activity.resultado
  if (activity.erros?.length) return activity.erros[0]
  if (activity.resultado && typeof activity.resultado === 'object') {
    return JSON.stringify(activity.resultado)
  }
  return activity.verificado ? 'Execucao verificada.' : 'Sem detalhes adicionais.'
}

  const [activities, setActivities] = useState<ActivityItem[]>([])
  const drawerRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  const reduceMotion = useReducedMotion()
  useEffect(() => {
    closeRef.current = onClose
  }, [onClose])


  useEffect(() => {
    if (!isOpen) return
    const previousFocus = document.activeElement as HTMLElement | null
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeRef.current()
        return
      }
      if (event.key !== 'Tab' || !drawerRef.current) return
      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
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
    window.requestAnimationFrame(() => drawerRef.current?.querySelector<HTMLElement>('button')?.focus())

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      previousFocus?.focus()
    }
  }, [isOpen])


  useEffect(() => {
    if (isOpen) {
      fetch('/api/execucoes/historico?limite=20')
        .then((r) => r.json())
        .then((data) => {
          if (data.execucoes) setActivities(data.execucoes)
        })
        .catch(() => {})
    }
  }, [isOpen])

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="drawer-layer">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.16 }}
            className="sheet-backdrop"
            onClick={() => closeRef.current()}
          />

          <motion.div
            initial={reduceMotion ? { opacity: 0 } : { x: '100%' }}
            ref={drawerRef}
            animate={{ x: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { x: '100%' }}
            transition={{ type: 'spring', damping: 34, stiffness: 380, mass: 0.82 }}
            className="activity-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Atividades da sessao"
            tabIndex={-1}
          >
            <div className="sheet-header">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-medium">Atividades da Sessão</h3>
              </div>
              <button onClick={() => closeRef.current()} className="sheet-close" aria-label="Fechar atividades">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="activity-list">
              {activities.length === 0 ? (
                <div className="text-center py-12 text-xs text-slate-500">
                  Nenhuma ferramenta executada nesta sessão ainda.
                </div>
              ) : (
                activities.map((act) => (
                  <article key={act.id_acao} className="activity-card">
                    <div className="flex items-center justify-between text-xs font-mono text-cyan-300">
                      <span className="flex items-center gap-1.5">
                        <Terminal className="w-3.5 h-3.5 text-cyan-400" />
                        {act.ferramenta || 'Ação'}
                      </span>
                      <time className="activity-time" dateTime={act.timestamp}>{formatTimestamp(act.timestamp)}</time>
                    </div>
                    <p className="activity-message">{describeResult(act)}</p>
                    <div className={`activity-result ${act.verificado ? 'verified' : 'unverified'}`}>
                      {act.verificado
                        ? <CheckCircle className="w-3 h-3" aria-hidden="true" />
                        : <CircleAlert className="w-3 h-3" aria-hidden="true" />}
                      <span>{act.verificado ? 'Verificada' : act.estado || 'Nao verificada'}</span>
                      {act.duracao_ms > 0 && <span>{Math.round(act.duracao_ms)} ms</span>}
                    </div>
                  </article>
                ))
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
