import React, { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, Mic, MicOff, Square } from 'lucide-react'

interface ChatInputProps {
  onSendMessage: (texto: string) => void
  disabled?: boolean
  isListening?: boolean
  onToggleVoice?: () => void
  isGenerating?: boolean
  onStop?: () => void
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  disabled = false,
  isListening = false,
  onToggleVoice,
  isGenerating = false,
  onStop
}) => {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    if (!text.trim() || disabled || isGenerating) return
    onSendMessage(text.trim())
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`
    }
  }, [text])

  return (
    <div className="composer-dock">
      <div className="composer">
        {/* Voice Trigger Toggle */}
        <motion.button
          type="button"
          whileHover={{ scale: 1.025 }}
          whileTap={{ scale: 0.97 }}
          onClick={onToggleVoice}
          className={`voice-button ${isListening ? 'active' : ''}`}
          aria-label={isListening ? 'Pausar escuta de voz' : 'Ativar escuta de voz'}
          aria-pressed={isListening}
          title={isListening ? 'Voz ativa: Ouvindo...' : 'Ativar microfone'}
        >
          {isListening ? <Mic className="w-4 h-4 animate-pulse" /> : <MicOff className="w-4 h-4" />}
        </motion.button>

        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Peça uma ordem para a Gideon..."
          rows={1}
          disabled={disabled}
          className="composer-input"
          aria-label="Mensagem para a Gideon"
          aria-describedby="composer-hint"
        />
        <span id="composer-hint" className="sr-only">Enter envia. Shift mais Enter cria uma nova linha.</span>

        {/* Send Button */}
        <motion.button
          type="button"
          whileHover={{ scale: 1.025 }}
          whileTap={{ scale: 0.97 }}
          onClick={isGenerating ? onStop : handleSend}
          disabled={isGenerating ? false : !text.trim() || disabled}
          className={`send-button ${isGenerating ? 'stop' : ''}`}
          aria-label={isGenerating ? 'Interromper resposta' : 'Enviar mensagem'}
        >
          {isGenerating ? <Square className="w-3.5 h-3.5" fill="currentColor" /> : <ArrowUp className="w-4 h-4" />}
        </motion.button>
      </div>
    </div>
  )
}
