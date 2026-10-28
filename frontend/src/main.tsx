import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'framer-motion'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user" transition={{ type: 'spring', stiffness: 360, damping: 34, mass: 0.8 }}>
      <App />
    </MotionConfig>
  </StrictMode>,
)
