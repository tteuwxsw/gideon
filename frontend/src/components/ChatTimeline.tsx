import React, { useEffect, useRef } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { Sparkles, Bot, User, Cpu } from 'lucide-react'
import type { Message } from '../types'

interface ChatTimelineProps {
  messages: Message[]
  isThinking: boolean
  onSelectSuggestion?: (texto: string) => void
}

export const ChatTimeline: React.FC<ChatTimelineProps> = ({
  messages,
  isThinking,
  onSelectSuggestion
}) => {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)
  const previousCountRef = useRef(0)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    const container = containerRef.current
    if (!container || !pinnedRef.current) return
    const newTurn = messages.length > previousCountRef.current
    previousCountRef.current = messages.length
    const frame = window.requestAnimationFrame(() => {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: newTurn && !reduceMotion ? 'smooth' : 'auto'
      })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [messages, isThinking, reduceMotion])

  const handleScroll = () => {
    const container = containerRef.current
    if (!container) return
    pinnedRef.current = container.scrollHeight - container.scrollTop - container.clientHeight < 80
  }

  if (messages.length === 0) {
    return (
      <motion.div
        className="welcome-copy"
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', damping: 30, stiffness: 360 }}
      >
        <div className="eyebrow-chip">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          <span>Nucleo de operacoes local</span>
        </div>
        <h2 className="hero-title">
          Às suas ordens, <span className="font-semibold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">Senhor Henry</span>.
        </h2>
        <p className="hero-subtitle">
          Posso operar o computador, telemetria em tempo real, automações e executar ordens verbais com máxima deferência.
        </p>

        {/* Suggestion Chips with Apple spring feedback */}
        <div className="prompt-grid">
          {[
            'Qual o consumo de memória e processador?',
            'Como está a previsão do tempo?',
            'Criar lembrete para amanhã cedo',
            'Status geral do sistema Windows'
          ].map((sug, i) => (
            <motion.button
              key={i}
              className="prompt-card"
              whileHover={reduceMotion ? undefined : { scale: 1.015 }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: 'spring', damping: 20, stiffness: 400 }}
              onClick={() => onSelectSuggestion?.(sug)}
            >
              <span className="prompt-index">0{i + 1}</span>
              <span>{sug}</span>
            </motion.button>
          ))}
        </div>
      </motion.div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="conversation-scroll"
      role="log"
      aria-label="Conversa com a Gideon"
      aria-busy={isThinking}
      onScroll={handleScroll}
    >
      <AnimatePresence initial={false}>
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 6 }}
            transition={{ type: 'spring', damping: 32, stiffness: 380 }}
            className={`message-row ${msg.role}`}
          >
            {msg.role === 'assistant' && (
              <div className="message-avatar assistant" aria-hidden="true">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`message-bubble ${msg.role}`}
            >
              <div className="message-content">
                {msg.content}
                {msg.isStreaming && Boolean(msg.content) && (
                  <motion.span
                    className="inline-block w-2 h-4 ml-1 bg-cyan-400 rounded-sm align-middle"
                    animate={reduceMotion ? { opacity: 0.8 } : { opacity: [1, 0.25, 1] }}
                    transition={{ repeat: reduceMotion ? 0 : Infinity, duration: 0.9 }}
                  />
                )}
              {msg.status === 'cancelled' && (
                <div className="message-state">Interrompida</div>
              )}
              </div>

              {/* Assistant Message Footnote */}
              {msg.role === 'assistant' && (msg.model || msg.latencyMs) && (
                <div className="message-meta">
                  <Cpu className="w-3 h-3 text-cyan-400/80" />
                  <span>{msg.model || 'gemini-flash-lite'}</span>
                  {msg.latencyMs && <span>• {Math.round(msg.latencyMs)}ms</span>}
                  {msg.tokens && <span>• {msg.tokens} tokens</span>}
                </div>
              )}
            </div>

            {msg.role === 'user' && (
              <div className="message-avatar user" aria-hidden="true">
                <User className="w-4 h-4" />
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Thinking Indicator */}
      {isThinking && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="thinking-state"
        >
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-amber-400"
                animate={reduceMotion ? { opacity: 0.75 } : { scale: [1, 1.35, 1], opacity: [0.4, 1, 0.4] }}
                transition={{ repeat: reduceMotion ? 0 : Infinity, duration: 0.9, delay: i * 0.16 }}
              />
            ))}
          </div>
          <span>Gideon está processando...</span>
        </motion.div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
