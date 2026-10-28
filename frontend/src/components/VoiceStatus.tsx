import React from 'react'
import { motion } from 'framer-motion'
import { Volume2, VolumeX } from 'lucide-react'
import type { ModoEscuta } from '../types'

interface VoiceStatusProps {
  isSpeaking: boolean
  isListening: boolean
  isThinking: boolean
  audioLevel: number
  connection?: 'connecting' | 'online' | 'offline'
  mode: ModoEscuta
  onToggleMute?: () => void
}

export const VoiceStatus: React.FC<VoiceStatusProps> = ({
  isSpeaking,
  isListening,
  isThinking,
  audioLevel,
  mode,
  connection = 'online',
  onToggleMute
}) => {
  const getModeLabel = () => {
    switch (mode) {
      case 'conversa_continua': return 'Contínua'
      case 'conversa_livre': return 'Livre'
      default: return 'Por Nome'
    }
  }

  const getStatusText = () => {
    if (connection === 'offline') return 'Reconectando'
    if (connection === 'connecting') return 'Sincronizando'
    if (isThinking) return 'Processando...'
    if (isSpeaking) return 'Gideon falando'
    if (isListening) return 'Ouvindo...'
    return 'Pronta'
  }

  return (
    <div className={`voice-status ${connection}`} role="status" aria-live="polite">
      <div className="flex items-center gap-0.5 h-3">
        {[0, 1, 2, 3].map((i) => {
          const scaleY = Math.max(0.2, audioLevel * (1 - i * 0.15))
          return (
            <motion.div
              key={i}
              className={`h-3.5 w-0.5 origin-bottom rounded-full ${
                isThinking ? 'bg-amber-400' : isSpeaking ? 'bg-emerald-400' : 'bg-cyan-400'
              }`}
              animate={{ scaleY }}
              transition={{ type: 'spring', damping: 22, stiffness: 420, mass: 0.5 }}
            />
          )
        })}
      </div>

      <span className="voice-status-copy">{getStatusText()}</span>
      <span className="voice-mode">{getModeLabel()}</span>

      <button
        onClick={onToggleMute}
        className="voice-interrupt"
        title="Silenciar áudio"
        disabled={!isSpeaking}
        aria-label="Interromper fala da Gideon"
      >
        {isSpeaking ? <Volume2 className="w-3.5 h-3.5 text-cyan-400" /> : <VolumeX className="w-3.5 h-3.5" />}
      </button>
    </div>
  )
}
