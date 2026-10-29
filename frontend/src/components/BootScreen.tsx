import React, { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

interface BootScreenProps {
  onComplete: () => void
}

const bootLines = [
  'Inicializando módulos...',
  'Verificando núcleo local...',
  'Sincronizando voz e memória...',
  'Gideon online'
]

export const BootScreen: React.FC<BootScreenProps> = ({ onComplete }) => {
  const [visibleLines, setVisibleLines] = useState(1)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    const intervalMs = reduceMotion ? 120 : 420
    const timers = bootLines.slice(1).map((_, index) =>
      window.setTimeout(() => setVisibleLines(index + 2), intervalMs * (index + 1))
    )
    const finishTimer = window.setTimeout(onComplete, reduceMotion ? 650 : 2100)
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer))
      window.clearTimeout(finishTimer)
    }
  }, [onComplete, reduceMotion])

  return (
    <main className="boot-screen" aria-label="Inicialização da Gideon">
      <div className="boot-core" aria-hidden="true">G</div>
      <div className="boot-log" role="status" aria-live="polite">
        {bootLines.slice(0, visibleLines).map((line, index) => (
          <p key={line} className={index === bootLines.length - 1 ? 'online' : ''}>
            <span aria-hidden="true">›</span> {line}
          </p>
        ))}
      </div>
      <button type="button" className="boot-skip" onClick={onComplete}>
        Pular
      </button>
    </main>
  )
}
