import React, { useEffect, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

interface HolographicOrbProps {
  audioLevel: number // 0.0 to 1.0
  isThinking: boolean
  isSpeaking: boolean
  isListening?: boolean
  compact?: boolean
  onClick?: () => void
  onLoadError?: (error: unknown) => void
}

interface AvatarState {
  audioLevel: number
  isThinking: boolean
  isSpeaking: boolean
  isListening: boolean
  compact: boolean
}

interface MorphMesh {
  dictionary: Record<string, number>
  influences: number[]
}

const disposeMaterial = (material: THREE.Material) => {
  for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) value.dispose()
  }
  material.dispose()
}

const disposeObject = (object: THREE.Object3D) => {
  const geometries = new Set<THREE.BufferGeometry>()
  const materials = new Set<THREE.Material>()

  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return
    geometries.add(child.geometry)
    const childMaterials = Array.isArray(child.material) ? child.material : [child.material]
    childMaterials.forEach((material) => materials.add(material))
  })

  geometries.forEach((geometry) => geometry.dispose())
  materials.forEach(disposeMaterial)
}

export const HolographicOrb: React.FC<HolographicOrbProps> = ({
  audioLevel,
  isThinking,
  isSpeaking,
  isListening = false,
  compact = false,
  onClick,
  onLoadError
}) => {
  const viewportRef = useRef<HTMLSpanElement>(null)
  const stateRef = useRef<AvatarState>({
    audioLevel,
    isThinking,
    isSpeaking,
    isListening,
    compact
  })
  const loadErrorRef = useRef(onLoadError)
  const [renderFailed, setRenderFailed] = useState(false)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    stateRef.current = { audioLevel, isThinking, isSpeaking, isListening, compact }
    loadErrorRef.current = onLoadError
  })

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

    let disposed = false
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: 'high-performance'
      })
    } catch (error) {
      queueMicrotask(() => {
        if (disposed) return
        setRenderFailed(true)
        loadErrorRef.current?.(error)
      })
      return () => {
        disposed = true
      }
    }

    let animationFrame = 0
    let avatarRoot: THREE.Group | null = null
    let loadedModel: THREE.Object3D | null = null
    let welcomeUntil = Number.POSITIVE_INFINITY
    let nextBlinkAt = performance.now() + 1800
    let previousFrame = performance.now()
    const morphMeshes: MorphMesh[] = []
    const pointer = new THREE.Vector2()

    renderer.setClearColor(0x000000, 0)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.2
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.width = '100%'
    viewport.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 30)
    camera.position.set(0, 0.02, 3.78)

    scene.add(new THREE.HemisphereLight(0x8afaff, 0x020712, 1.3))
    const keyLight = new THREE.DirectionalLight(0xb9fcff, 2.4)
    keyLight.position.set(1.8, 2.6, 3.5)
    scene.add(keyLight)
    const rimLight = new THREE.PointLight(0x007cff, 8, 8)
    rimLight.position.set(-2.2, 0.6, -1.2)
    scene.add(rimLight)

    const particleCount = stateRef.current.compact ? 42 : 72
    const particlePositions = new Float32Array(particleCount * 3)
    for (let index = 0; index < particleCount; index += 1) {
      const radius = 1.18 + Math.random() * 0.62
      const angle = Math.random() * Math.PI * 2
      particlePositions[index * 3] = Math.cos(angle) * radius
      particlePositions[index * 3 + 1] = (Math.random() - 0.5) * 2.8
      particlePositions[index * 3 + 2] = (Math.random() - 0.5) * 0.9 - 0.35
    }
    const particleGeometry = new THREE.BufferGeometry()
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3))
    const particleMaterial = new THREE.PointsMaterial({
      color: 0x61efff,
      size: stateRef.current.compact ? 0.022 : 0.028,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    })
    const particles = new THREE.Points(particleGeometry, particleMaterial)
    scene.add(particles)

    const bodyMaterial = new THREE.MeshStandardMaterial({
      color: 0x43cfe3,
      emissive: 0x087e9c,
      emissiveIntensity: 0.62,
      metalness: 0.18,
      roughness: 0.46,
      transparent: true,
      opacity: 0.92
    })
    const eyeMaterial = new THREE.MeshStandardMaterial({
      color: 0xd9ffff,
      emissive: 0x22dff5,
      emissiveIntensity: 1.45,
      metalness: 0.05,
      roughness: 0.24,
      transparent: true,
      opacity: 0.98
    })

    const fail = (error: unknown) => {
      if (disposed) return
      setRenderFailed(true)
      loadErrorRef.current?.(error)
    }
    const handleContextLoss = (event: Event) => {
      event.preventDefault()
      fail(new Error('O contexto WebGL do avatar foi perdido.'))
    }
    renderer.domElement.addEventListener('webglcontextlost', handleContextLoss)

    new GLTFLoader().load(
      '/avatar/gideon-head.glb',
      (gltf) => {
        if (disposed) {
          disposeObject(gltf.scene)
          return
        }

        const bounds = new THREE.Box3().setFromObject(gltf.scene)
        if (bounds.isEmpty()) {
          disposeObject(gltf.scene)
          fail(new Error('O modelo 3D da Gideon nao contem geometria renderizavel.'))
          return
        }

        const originalMaterials = new Set<THREE.Material>()
        gltf.scene.traverse((child) => {
          if (!(child instanceof THREE.Mesh)) return

          const childMaterials = Array.isArray(child.material) ? child.material : [child.material]
          childMaterials.forEach((material) => originalMaterials.add(material))
          child.material = child.name.toLowerCase().includes('eyes') ? eyeMaterial : bodyMaterial

          if (child.morphTargetDictionary && child.morphTargetInfluences) {
            morphMeshes.push({
              dictionary: child.morphTargetDictionary,
              influences: child.morphTargetInfluences
            })
          }
        })
        originalMaterials.forEach(disposeMaterial)

        const center = bounds.getCenter(new THREE.Vector3())
        const size = bounds.getSize(new THREE.Vector3())
        const scale = 2.3 / Math.max(size.y, size.x * 1.12, size.z)
        gltf.scene.position.copy(center).multiplyScalar(-1)

        avatarRoot = new THREE.Group()
        avatarRoot.scale.setScalar(scale)
        avatarRoot.add(gltf.scene)
        scene.add(avatarRoot)
        loadedModel = gltf.scene
        welcomeUntil =
          stateRef.current.isSpeaking || stateRef.current.isThinking
            ? 0
            : performance.now() + 3200
      },
      undefined,
      fail
    )

    const resize = () => {
      const width = Math.max(1, viewport.clientWidth)
      const height = Math.max(1, viewport.clientHeight)
      const pixelRatioCap = stateRef.current.compact ? 1.5 : 2
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, pixelRatioCap))
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(viewport)
    resize()

    const trackPointer = (event: PointerEvent) => {
      if (event.pointerType === 'touch') return
      const bounds = viewport.getBoundingClientRect()
      pointer.set(
        THREE.MathUtils.clamp(((event.clientX - bounds.left) / bounds.width) * 2 - 1, -1, 1),
        THREE.MathUtils.clamp(-(((event.clientY - bounds.top) / bounds.height) * 2 - 1), -1, 1)
      )
    }
    const resetPointer = () => pointer.set(0, 0)
    viewport.addEventListener('pointermove', trackPointer)
    viewport.addEventListener('pointerleave', resetPointer)

    const setMorph = (name: string, target: number, delta: number) => {
      for (const mesh of morphMeshes) {
        const index = mesh.dictionary[name]
        if (index === undefined) continue
        mesh.influences[index] = THREE.MathUtils.damp(
          mesh.influences[index] ?? 0,
          target,
          name.startsWith('Blink') ? 28 : 10,
          delta
        )
      }
    }

    const animate = (now: number) => {
      if (reduceMotion && now - previousFrame < 100) {
        animationFrame = requestAnimationFrame(animate)
        return
      }
      if (disposed) return
      const delta = Math.min((now - previousFrame) / 1000, 0.05)
      previousFrame = now
      const seconds = now / 1000
      const currentState = stateRef.current
      const audio = THREE.MathUtils.clamp(currentState.audioLevel || 0, 0, 1)

      let blink = 0
      if (now >= nextBlinkAt) {
        const blinkProgress = (now - nextBlinkAt) / 180
        if (blinkProgress <= 1) {
          blink = Math.sin(blinkProgress * Math.PI)
        } else {
          nextBlinkAt = now + 2200 + Math.random() * 3200
        }
      }

      const speechPulse = (Math.sin(seconds * 11.5) + Math.sin(seconds * 17.2 + 0.8) + 2) / 4
      const mouthOpen = currentState.isSpeaking
        ? THREE.MathUtils.clamp(0.1 + audio * 0.72 + speechPulse * 0.22, 0, 0.94)
        : 0
      const narrow = currentState.isSpeaking ? 0.08 + (1 - audio) * speechPulse * 0.28 : 0
      const midmouthLeft = currentState.isSpeaking ? 0.08 + Math.max(0, Math.sin(seconds * 7.7)) * 0.22 : 0
      const midmouthRight = currentState.isSpeaking ? 0.08 + Math.max(0, Math.sin(seconds * 7.7 + 1.4)) * 0.22 : 0
      const welcomeSmile = now < welcomeUntil ? 0.48 : 0
      const thinkingPulse = currentState.isThinking ? 0.04 * (Math.sin(seconds * 2.8) + 1) : 0

      setMorph('Blink_Left', blink, delta)
      setMorph('Blink_Right', blink, delta)
      setMorph('MouthOpen', mouthOpen, delta)
      setMorph('MouthNarrow_Left', narrow, delta)
      setMorph('MouthNarrow_Right', narrow, delta)
      setMorph('Midmouth_Left', midmouthLeft, delta)
      setMorph('Midmouth_Right', midmouthRight, delta)
      setMorph('Smile_Left', welcomeSmile, delta)
      setMorph('Smile_Right', welcomeSmile, delta)
      setMorph('BrowsUp_Left', currentState.isThinking ? 0.32 + thinkingPulse : 0, delta)
      setMorph('BrowsUp_Right', currentState.isThinking ? 0.32 + thinkingPulse : 0, delta)
      setMorph('BrowsIn_Left', currentState.isThinking ? 0.2 : 0, delta)
      setMorph('BrowsIn_Right', currentState.isThinking ? 0.2 : 0, delta)
      setMorph('EyesWide_Left', currentState.isListening ? 0.24 : 0, delta)
      setMorph('EyesWide_Right', currentState.isListening ? 0.24 : 0, delta)

      if (avatarRoot) {
        const targetX = reduceMotion ? 0 : pointer.y * 0.07 + Math.sin(seconds * 0.72) * 0.018
        const targetY = reduceMotion ? 0 : pointer.x * 0.13 + Math.sin(seconds * 0.45) * 0.035
        avatarRoot.rotation.x = THREE.MathUtils.damp(avatarRoot.rotation.x, targetX, 4.5, delta)
        avatarRoot.rotation.y = THREE.MathUtils.damp(avatarRoot.rotation.y, targetY, 4.5, delta)
        avatarRoot.rotation.z = THREE.MathUtils.damp(
          avatarRoot.rotation.z,
          reduceMotion ? 0 : Math.sin(seconds * 0.55) * 0.012,
          3,
          delta
        )
        avatarRoot.position.y = THREE.MathUtils.damp(
          avatarRoot.position.y,
          reduceMotion ? 0 : Math.sin(seconds * 0.9) * 0.035,
          3.5,
          delta
        )
      }

      if (!reduceMotion) {
        particles.rotation.y += delta * 0.045
        particles.rotation.z = Math.sin(seconds * 0.22) * 0.025
      }
      particleMaterial.opacity = 0.46 + audio * 0.22
      renderer.render(scene, camera)
      animationFrame = requestAnimationFrame(animate)
    }
    animationFrame = requestAnimationFrame(animate)

    return () => {
      disposed = true
      cancelAnimationFrame(animationFrame)
      resizeObserver.disconnect()
      viewport.removeEventListener('pointermove', trackPointer)
      viewport.removeEventListener('pointerleave', resetPointer)
      renderer.domElement.removeEventListener('webglcontextlost', handleContextLoss)
      if (loadedModel) disposeObject(loadedModel)
      particleGeometry.dispose()
      particleMaterial.dispose()
      bodyMaterial.dispose()
      eyeMaterial.dispose()
      renderer.renderLists.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
      renderer.domElement.remove()
    }
  }, [reduceMotion])

  const normalizedAudioLevel = Math.min(1, Math.max(0, audioLevel || 0))
  const portraitScale = reduceMotion ? 1 : 1 + normalizedAudioLevel * (isSpeaking ? 0.045 : 0.02)

  const glow = isSpeaking
    ? {
        color: 'rgba(0, 255, 180, 0.48)',
        edge: 'rgba(45, 255, 196, 0.72)',
        shadow: 'rgba(0, 255, 180, 0.58)'
      }
    : isThinking
      ? {
          color: 'rgba(255, 170, 0, 0.42)',
          edge: 'rgba(255, 190, 58, 0.68)',
          shadow: 'rgba(255, 145, 0, 0.52)'
        }
      : isListening
        ? {
            color: 'rgba(0, 243, 255, 0.42)',
            edge: 'rgba(79, 244, 255, 0.68)',
            shadow: 'rgba(0, 243, 255, 0.54)'
          }
        : {
            color: 'rgba(0, 102, 255, 0.3)',
            edge: 'rgba(77, 154, 255, 0.46)',
            shadow: 'rgba(0, 102, 255, 0.4)'
          }

  return (
    <motion.button
      type="button"
      className={`relative flex shrink-0 cursor-pointer select-none items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/80 ${
        compact
          ? 'h-24 w-24 sm:h-28 sm:w-28'
          : 'h-48 w-48 sm:h-56 sm:w-56 md:h-64 md:w-64'
      }`}
      animate={{ scale: portraitScale }}
      transition={{ type: 'spring', stiffness: 280, damping: 20, mass: 0.7 }}
      whileHover={reduceMotion ? undefined : { scale: portraitScale * 1.035 }}
      whileTap={reduceMotion ? undefined : { scale: portraitScale * 0.96 }}
      onClick={onClick}
      title="Clique para alternar escuta de voz da Gideon"
      aria-label="Alternar escuta de voz da Gideon"
    >
      aria-pressed={isListening}
      <motion.span
        className="pointer-events-none absolute inset-[8%] rounded-full blur-2xl"
        animate={{
          opacity: 0.68 + normalizedAudioLevel * 0.24,
          scale: 1.02 + normalizedAudioLevel * 0.08,
          backgroundColor: glow.color
        }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      />

      <motion.span
        className="pointer-events-none absolute inset-[5%] rounded-full border"
        style={{ borderColor: glow.edge, boxShadow: `0 0 24px ${glow.shadow}` }}
        animate={{ rotate: reduceMotion ? 0 : 360 }}
        transition={{ duration: isThinking ? 5 : 9, ease: 'linear', repeat: reduceMotion ? 0 : Infinity }}
      >
        <span
          className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full"
          style={{ backgroundColor: glow.edge, boxShadow: `0 0 12px ${glow.shadow}` }}
        />
      </motion.span>

      <span
        className="relative h-[84%] w-[84%] overflow-hidden rounded-full border bg-[#07101d]/90 backdrop-blur-sm"
        style={{
          borderColor: glow.edge,
          boxShadow: `inset 0 0 24px rgba(0, 10, 24, 0.9), 0 0 30px ${glow.shadow}`
        }}
      >
        <span ref={viewportRef} className="absolute inset-0" aria-hidden="true" />

        {renderFailed && (
          <span className="absolute inset-0 flex flex-col items-center justify-center bg-[radial-gradient(circle,rgba(0,243,255,0.2),rgba(4,10,22,0.96)_68%)] text-cyan-200">
            <span className={compact ? 'text-2xl font-light' : 'text-5xl font-light'}>G</span>
            <span className="mt-1 font-mono text-[8px] tracking-[0.28em] opacity-70">GIDEON</span>
          </span>
        )}

        <span className="pointer-events-none absolute inset-0 bg-[linear-gradient(110deg,transparent_25%,rgba(184,251,255,0.13)_47%,transparent_62%)] mix-blend-screen" />
        <motion.span
          className="pointer-events-none absolute inset-x-0 top-0 h-[18%] bg-gradient-to-b from-transparent via-cyan-100/20 to-transparent mix-blend-screen"
          animate={reduceMotion ? { opacity: 0 } : { y: ['-100%', '650%'] }}
          transition={{ duration: 3.6, ease: 'linear', repeat: reduceMotion ? 0 : Infinity }}
        />
        <span
          className="pointer-events-none absolute inset-0 opacity-20 mix-blend-screen"
          style={{
            backgroundImage:
              'repeating-linear-gradient(to bottom, transparent 0, transparent 3px, rgba(116, 240, 255, 0.2) 4px)'
          }}
        />
        <span className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-[#07101d]/85 to-transparent" />
      </span>
    </motion.button>
  )
}