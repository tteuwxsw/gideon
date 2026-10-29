import React, { useEffect, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'

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

const keepOuterFaceShell = (geometry: THREE.BufferGeometry) => {
  const index = geometry.getIndex()
  const position = geometry.getAttribute('position')
  if (!index || !position) return

  const parent = new Int32Array(position.count)
  const sizes = new Int32Array(position.count)
  for (let i = 0; i < position.count; i += 1) {
    parent[i] = i
    sizes[i] = 1
  }
  const find = (start: number) => {
    let node = start
    while (parent[node] !== node) {
      parent[node] = parent[parent[node]]
      node = parent[node]
    }
    return node
  }
  const union = (a: number, b: number) => {
    let rootA = find(a)
    let rootB = find(b)
    if (rootA === rootB) return
    if (sizes[rootA] < sizes[rootB]) [rootA, rootB] = [rootB, rootA]
    parent[rootB] = rootA
    sizes[rootA] += sizes[rootB]
  }

  for (let i = 0; i < index.count; i += 3) {
    const a = index.getX(i)
    const b = index.getX(i + 1)
    const c = index.getX(i + 2)
    union(a, b)
    union(b, c)
  }
  let outerRoot = 0
  for (let i = 1; i < position.count; i += 1) {
    if (sizes[find(i)] > sizes[find(outerRoot)]) outerRoot = i
  }
  outerRoot = find(outerRoot)

  const outerIndices: number[] = []
  for (let i = 0; i < index.count; i += 3) {
    const a = index.getX(i)
    if (find(a) !== outerRoot) continue
    outerIndices.push(a, index.getX(i + 1), index.getX(i + 2))
  }
  geometry.setIndex(outerIndices)
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
    if (!(child instanceof THREE.Mesh || child instanceof THREE.Points || child instanceof THREE.LineSegments)) return
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
    let smoothedAudio = 0
    const morphMeshes: MorphMesh[] = []
    const eyeTrackers: THREE.Group[] = []
    const pointer = new THREE.Vector2()
    let particleCloud: THREE.Points | null = null
    let lipRig: {
      group: THREE.Group
      upper: THREE.Mesh
      lower: THREE.Mesh
      interior: THREE.Mesh
    } | null = null

    renderer.setClearColor(0x000000, 0)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 0.84
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.width = '100%'
    viewport.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 30)
    camera.position.set(0, 0.015, 3.48)
    const composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.22, 0.32, 0.62)
    composer.addPass(bloomPass)

    scene.add(new THREE.HemisphereLight(0xbcecf2, 0x02070a, 0.4))
    const keyLight = new THREE.DirectionalLight(0xe9fcff, 1.45)
    keyLight.position.set(1.55, 2.15, 3.1)
    scene.add(keyLight)
    const fillLight = new THREE.DirectionalLight(0x3b8f9d, 0.28)
    fillLight.position.set(-1.8, -0.25, 2.4)
    scene.add(fillLight)
    const rimLight = new THREE.PointLight(0x55d9eb, 1.5, 7)
    rimLight.position.set(-2.1, 0.7, -1.3)
    scene.add(rimLight)

    const bodyMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x28a9b7,
      emissive: 0x03424a,
      emissiveIntensity: 0.16,
      metalness: 0.06,
      roughness: 0.4,
      clearcoat: 0.3,
      clearcoatRoughness: 0.5,
      iridescence: 0.1,
      iridescenceIOR: 1.1,
      transparent: true,
      opacity: 0.68,
      side: THREE.FrontSide,
      depthWrite: true
    })
    const eyeMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x237f8c,
      emissive: 0x0b4d56,
      emissiveIntensity: 0.2,
      metalness: 0,
      roughness: 0.26,
      clearcoat: 0.38,
      transparent: true,
      opacity: 0.68,
      side: THREE.DoubleSide,
      depthWrite: false
    })
    const hologramUniforms = {
      uHoloTime: { value: 0 }
    }
    bodyMaterial.onBeforeCompile = (shader) => {
      shader.uniforms.uHoloTime = hologramUniforms.uHoloTime
      shader.vertexShader = shader.vertexShader
        .replace(
          '#include <common>',
          `#include <common>
          varying vec3 vHoloLocal;
          varying vec3 vHoloWorld;
          varying vec3 vHoloNormal;`
        )
        .replace(
          '#include <morphtarget_vertex>',
          `#include <morphtarget_vertex>
          vHoloLocal = transformed;
          vHoloWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
          vHoloNormal = normalize(mat3(modelMatrix) * objectNormal);`
        )
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          `#include <common>
          uniform float uHoloTime;
          varying vec3 vHoloLocal;
          varying vec3 vHoloWorld;
          varying vec3 vHoloNormal;
          float gideonHash(vec2 p) {
            return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
          }`
        )
        .replace(
          '#include <dithering_fragment>',
          `float holoFresnel = pow(1.0 - abs(dot(normalize(vHoloNormal), normalize(cameraPosition - vHoloWorld))), 2.35);
          float holoScan = 0.5 + 0.5 * sin((vHoloLocal.y + uHoloTime * 0.026) * 285.0);
          float holoContour = pow(0.5 + 0.5 * sin((length(vHoloLocal.xz) + vHoloLocal.y * 0.24) * 18.0), 14.0);
          float holoFlicker = 0.965 + 0.035 * sin(uHoloTime * 17.0 + vHoloLocal.y * 41.0);
          float neckFade = smoothstep(-1.18, -0.72, vHoloLocal.y);
          vec3 hologramLight = vec3(0.0, 0.898, 1.0) * (0.065 + holoFresnel * 0.44);
          hologramLight += vec3(0.18, 0.76, 0.9) * holoContour * 0.055;
          hologramLight += vec3(0.0, 0.62, 0.72) * holoScan * 0.018;
          gl_FragColor.rgb = gl_FragColor.rgb * holoFlicker + hologramLight;
          gl_FragColor.b += holoFresnel * 0.055;
          gl_FragColor.a *= neckFade * (0.64 + holoFresnel * 0.28) * (0.92 + holoScan * 0.08);
          #include <dithering_fragment>`
        )
    }
    bodyMaterial.customProgramCacheKey = () => 'gideon-hologram-v1'

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
          const isEyeMesh = child.name.toLowerCase().includes('eyes')
          child.material = isEyeMesh ? eyeMaterial : bodyMaterial
          child.visible = !isEyeMesh
          if (!isEyeMesh) keepOuterFaceShell(child.geometry)

          if (child.morphTargetDictionary && child.morphTargetInfluences) {
            morphMeshes.push({
              dictionary: child.morphTargetDictionary,
              influences: child.morphTargetInfluences
            })
          }
        })
        originalMaterials.forEach(disposeMaterial)

        const particlePositions: number[] = []
        for (let i = 0; i < 88; i += 1) {
          const theta = Math.random() * Math.PI * 2
          const y = -1.08 + Math.random() * 2.12
          const radiusAtY = Math.sqrt(Math.max(0.08, 1 - Math.pow(y / 1.2, 2)))
          const distance = 1.02 + Math.random() * 0.1
          particlePositions.push(
            Math.cos(theta) * 0.77 * radiusAtY * distance,
            y + Math.random() * 0.025,
            Math.sin(theta) * 0.88 * radiusAtY * distance
          )
        }
        for (let i = 0; i < 34; i += 1) {
          const y = -1.22 + Math.random() * 0.46
          const width = 0.16 + (y + 1.22) * 0.72
          particlePositions.push(
            (Math.random() * 2 - 1) * width,
            y,
            0.18 + Math.random() * 0.62
          )
        }
        const particleGeometry = new THREE.BufferGeometry()
        particleGeometry.setAttribute('position', new THREE.Float32BufferAttribute(particlePositions, 3))
        const particleMaterial = new THREE.PointsMaterial({
          color: 0x62efff,
          size: 0.009,
          sizeAttenuation: true,
          transparent: true,
          opacity: 0.28,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        })
        particleCloud = new THREE.Points(particleGeometry, particleMaterial)
        particleCloud.name = 'GideonSurfaceData'
        gltf.scene.add(particleCloud)

        // O GLB traz globos sem íris. Estes detalhes permanecem dentro da
        // geometria facial e transformam o olhar sem adicionar efeitos externos.
        const irisMaterial = new THREE.MeshPhysicalMaterial({
          color: 0x35becb,
          emissive: 0x137984,
          emissiveIntensity: 0.34,
          roughness: 0.3,
          clearcoat: 0.55,
          transparent: true,
          opacity: 0.9,
          side: THREE.DoubleSide
        })
        const eyeGlowMaterial = new THREE.MeshBasicMaterial({
          color: 0x6cebf5,
          transparent: true,
          opacity: 0.5,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide
        })
        const pupilMaterial = new THREE.MeshBasicMaterial({
          color: 0x061012,
          transparent: true,
          opacity: 0.9,
          side: THREE.DoubleSide
        })
        const catchlightMaterial = new THREE.MeshBasicMaterial({
          color: 0xe9ffff,
          transparent: true,
          opacity: 0.82,
          side: THREE.DoubleSide
        })
        const eyeShape = new THREE.Shape()
        eyeShape.moveTo(-0.105, 0)
        eyeShape.bezierCurveTo(-0.055, 0.058, 0.055, 0.058, 0.105, 0)
        eyeShape.bezierCurveTo(0.052, -0.048, -0.052, -0.048, -0.105, 0)
        const eyeGeometry = new THREE.ShapeGeometry(eyeShape, 24)
        const eyebrowMaterial = new THREE.MeshBasicMaterial({
          color: 0x73f3ff,
          transparent: true,
          opacity: 0.48,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        })
        for (const x of [-0.291, 0.291]) {
          const eye = new THREE.Group()
          eye.position.set(x, 0.159, 0.642)
          eye.userData.baseX = x
          eye.userData.baseY = 0.159

          const eyeGlow = new THREE.Mesh(eyeGeometry, eyeGlowMaterial)
          eye.add(eyeGlow)

          const iris = new THREE.Mesh(new THREE.CircleGeometry(0.038, 32), irisMaterial)
          iris.scale.y = 0.9
          iris.position.z = 0.002
          eye.add(iris)

          const pupil = new THREE.Mesh(new THREE.CircleGeometry(0.014, 24), pupilMaterial)
          pupil.position.z = 0.004
          eye.add(pupil)

          const catchlight = new THREE.Mesh(new THREE.CircleGeometry(0.006, 16), catchlightMaterial)
          catchlight.position.set(-0.009, 0.011, 0.006)
          eye.add(catchlight)

          eyeTrackers.push(eye)
          gltf.scene.add(eye)

          const eyebrowCurve = new THREE.QuadraticBezierCurve3(
            new THREE.Vector3(x - 0.098, 0.295, 0.638),
            new THREE.Vector3(x, 0.352, 0.658),
            new THREE.Vector3(x + 0.098, 0.302, 0.638)
          )
          const eyebrow = new THREE.Mesh(
            new THREE.TubeGeometry(eyebrowCurve, 20, 0.005, 6, false),
            eyebrowMaterial
          )
          eyebrow.name = 'GideonEyebrow'
          gltf.scene.add(eyebrow)
        }

        const mouthGroup = new THREE.Group()
        mouthGroup.position.set(0, -0.445, 1.015)
        const mouthCoverMaterial = new THREE.MeshPhysicalMaterial({
          color: 0x28a9b7,
          emissive: 0x03424a,
          emissiveIntensity: 0.16,
          roughness: 0.4,
          metalness: 0.06,
          transparent: true,
          opacity: 0.86,
          depthWrite: true,
          side: THREE.DoubleSide
        })
        const mouthInteriorMaterial = new THREE.MeshBasicMaterial({
          color: 0x001316,
          transparent: true,
          opacity: 0.88,
          depthWrite: false,
          side: THREE.DoubleSide
        })
        const lipMaterial = new THREE.MeshBasicMaterial({
          color: 0x68e6ef,
          transparent: true,
          opacity: 0.62,
          depthWrite: false,
          side: THREE.DoubleSide
        })
        const cover = new THREE.Mesh(new THREE.CircleGeometry(1, 40), mouthCoverMaterial)
        cover.scale.set(0.255, 0.15, 1)
        mouthGroup.add(cover)

        const interior = new THREE.Mesh(new THREE.CircleGeometry(1, 32), mouthInteriorMaterial)
        interior.position.z = 0.002
        interior.scale.set(0.155, 0.007, 1)
        mouthGroup.add(interior)

        const upperCurve = new THREE.CatmullRomCurve3(
          [
            new THREE.Vector3(-0.15, 0, 0),
            new THREE.Vector3(-0.075, 0.01, 0),
            new THREE.Vector3(0, 0.018, 0),
            new THREE.Vector3(0.075, 0.01, 0),
            new THREE.Vector3(0.15, 0, 0)
          ],
          false,
          'centripetal'
        )
        const upper = new THREE.Mesh(new THREE.TubeGeometry(upperCurve, 32, 0.005, 6, false), lipMaterial)
        upper.position.z = 0.004
        mouthGroup.add(upper)

        const lowerCurve = new THREE.CatmullRomCurve3(
          [
            new THREE.Vector3(-0.15, -0.003, 0),
            new THREE.Vector3(-0.075, -0.014, 0),
            new THREE.Vector3(0, -0.024, 0),
            new THREE.Vector3(0.075, -0.014, 0),
            new THREE.Vector3(0.15, -0.003, 0)
          ],
          false,
          'centripetal'
        )
        const lower = new THREE.Mesh(new THREE.TubeGeometry(lowerCurve, 32, 0.005, 6, false), lipMaterial)
        lower.position.z = 0.004
        mouthGroup.add(lower)

        lipRig = { group: mouthGroup, upper, lower, interior }
        gltf.scene.add(mouthGroup)

        const center = bounds.getCenter(new THREE.Vector3())
        const size = bounds.getSize(new THREE.Vector3())
        const scale = 2.3 / Math.max(size.y, size.x * 1.12, size.z)
        gltf.scene.position.copy(center).multiplyScalar(-1)

        avatarRoot = new THREE.Group()
        avatarRoot.scale.set(scale * 0.94, scale, scale)
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
      composer.setPixelRatio(Math.min(window.devicePixelRatio || 1, pixelRatioCap))
      composer.setSize(width, height)
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
      hologramUniforms.uHoloTime.value = seconds
      const audioTarget = THREE.MathUtils.clamp(currentState.audioLevel || 0, 0, 1)
      smoothedAudio = THREE.MathUtils.damp(smoothedAudio, audioTarget, 18, delta)
      const audio = smoothedAudio

      let blink = 0
      if (now >= nextBlinkAt) {
        const blinkProgress = (now - nextBlinkAt) / 180
        if (blinkProgress <= 1) {
          blink = Math.sin(blinkProgress * Math.PI)
        } else {
          nextBlinkAt = now + 2200 + Math.random() * 3200
        }
      }

      const speechPulse = (Math.sin(seconds * 9.7) + Math.sin(seconds * 14.3 + 0.8) + 2) / 4
      const mouthOpen = currentState.isSpeaking
        ? THREE.MathUtils.clamp(0.025 + audio * 0.6 + speechPulse * audio * 0.14, 0, 0.68)
        : 0
      const welcomeSmile = now < welcomeUntil ? 0.045 : 0
      const idleSmile = currentState.isListening ? 0.018 : 0.006
      const thinkingPulse = currentState.isThinking ? 0.04 * (Math.sin(seconds * 2.8) + 1) : 0
      const articulation = currentState.isSpeaking ? THREE.MathUtils.smoothstep(audio, 0.025, 0.32) : 0
      const visemeA = articulation * Math.max(0, Math.sin(seconds * 8.1))
      const visemeE = articulation * Math.max(0, Math.sin(seconds * 7.3 + 1.55))
      const visemeO = articulation * Math.max(0, Math.sin(seconds * 6.7 + 3.1))
      const visemeM = articulation * Math.max(0, Math.sin(seconds * 9.1 + 4.65))

      setMorph('Blink_Left', blink, delta)
      setMorph('Blink_Right', blink, delta)
      setMorph('MouthOpen', 0, delta)
      setMorph('Jaw_Down', currentState.isSpeaking ? mouthOpen * 0.08 : 0, delta)
      setMorph('MouthNarrow_Left', 0, delta)
      setMorph('MouthNarrow_Right', 0, delta)
      setMorph('MouthWhistle_NarrowAdjust_Left', 0, delta)
      setMorph('MouthWhistle_NarrowAdjust_Right', 0, delta)
      setMorph('Midmouth_Left', 0, delta)
      setMorph('Midmouth_Right', 0, delta)
      setMorph('Smile_Left', Math.max(welcomeSmile, idleSmile, visemeE * 0.1), delta)
      setMorph('Smile_Right', Math.max(welcomeSmile, idleSmile, visemeE * 0.1), delta)
      setMorph('UpperLipOut', 0, delta)
      setMorph('UpperLipIn', 0, delta)
      setMorph('LowerLipOut', 0, delta)
      setMorph('LowerLipIn', 0, delta)
      setMorph('LowerLipDown_Left', 0, delta)
      setMorph('LowerLipDown_Right', 0, delta)
      setMorph('UpperLipUp_Left', 0, delta)
      setMorph('UpperLipUp_Right', 0, delta)
      setMorph('MouthUp', 0, delta)
      setMorph('MouthDown', 0, delta)
      setMorph('BrowsUp_Left', currentState.isThinking ? 0.12 + thinkingPulse : 0, delta)
      setMorph('BrowsUp_Right', currentState.isThinking ? 0.12 + thinkingPulse : 0, delta)
      setMorph('BrowsIn_Left', currentState.isThinking ? 0.09 : 0, delta)
      setMorph('BrowsIn_Right', currentState.isThinking ? 0.09 : 0, delta)
      setMorph('EyesWide_Left', currentState.isListening ? 0.07 : 0, delta)
      setMorph('EyesWide_Right', currentState.isListening ? 0.07 : 0, delta)

      if (lipRig) {
        const opening = currentState.isSpeaking
          ? mouthOpen * (0.7 + visemeA * 0.3) * (1 - visemeM * 0.78)
          : 0
        const width = 1 + visemeE * 0.1 - visemeO * 0.16
        lipRig.group.scale.x = THREE.MathUtils.damp(lipRig.group.scale.x, width, 14, delta)
        lipRig.upper.position.y = THREE.MathUtils.damp(lipRig.upper.position.y, opening * 0.024, 18, delta)
        lipRig.lower.position.y = THREE.MathUtils.damp(lipRig.lower.position.y, -0.004 - opening * 0.05, 18, delta)
        lipRig.interior.scale.x = THREE.MathUtils.damp(lipRig.interior.scale.x, 0.155 * width, 14, delta)
        lipRig.interior.scale.y = THREE.MathUtils.damp(
          lipRig.interior.scale.y,
          0.007 + opening * 0.075 + visemeO * 0.02,
          18,
          delta
        )
      }

      const automaticLookX = currentState.isThinking ? Math.sin(seconds * 0.9) * 0.012 : 0
      const automaticLookY = currentState.isThinking ? 0.009 : 0
      for (const eye of eyeTrackers) {
        const targetEyeX = eye.userData.baseX + pointer.x * 0.018 + automaticLookX
        const targetEyeY = eye.userData.baseY + pointer.y * 0.012 + automaticLookY
        eye.position.x = THREE.MathUtils.damp(eye.position.x, targetEyeX, 10, delta)
        eye.position.y = THREE.MathUtils.damp(eye.position.y, targetEyeY, 10, delta)
        eye.scale.y = THREE.MathUtils.damp(eye.scale.y, Math.max(0.035, 1 - blink * 1.08), 24, delta)
      }

      const energiaVisual = currentState.isSpeaking
        ? 0.12 + audio * 0.16
        : currentState.isThinking || currentState.isListening ? 0.15 : 0.1
      bodyMaterial.emissiveIntensity = THREE.MathUtils.damp(
        bodyMaterial.emissiveIntensity,
        Math.max(0.1, energiaVisual * 0.72),
        4,
        delta
      )
      eyeMaterial.emissiveIntensity = THREE.MathUtils.damp(
        eyeMaterial.emissiveIntensity,
        currentState.isListening ? 0.32 : currentState.isSpeaking ? 0.27 : 0.2,
        5,
        delta
      )
      rimLight.intensity = THREE.MathUtils.damp(
        rimLight.intensity,
        currentState.isThinking ? 1.85 : currentState.isSpeaking ? 1.7 : 1.5,
        3,
        delta
      )
      bloomPass.strength = THREE.MathUtils.damp(
        bloomPass.strength,
        currentState.isSpeaking ? 0.28 + audio * 0.07 : currentState.isThinking ? 0.31 : 0.22,
        3,
        delta
      )
      if (particleCloud && !reduceMotion) {
        particleCloud.rotation.y = Math.sin(seconds * 0.13) * 0.018
        particleCloud.position.y = ((seconds * 0.018) % 0.05) - 0.025
      }

      if (avatarRoot) {
        const targetX = reduceMotion ? 0 : pointer.y * 0.055 + Math.sin(seconds * 0.62) * 0.009
        const targetY = reduceMotion ? 0 : pointer.x * 0.11 + Math.sin(seconds * 0.38) * 0.018
        avatarRoot.rotation.x = THREE.MathUtils.damp(avatarRoot.rotation.x, targetX, 4.5, delta)
        avatarRoot.rotation.y = THREE.MathUtils.damp(avatarRoot.rotation.y, targetY, 4.5, delta)
        avatarRoot.rotation.z = THREE.MathUtils.damp(
          avatarRoot.rotation.z,
          reduceMotion ? 0 : Math.sin(seconds * 0.48) * 0.006,
          3,
          delta
        )
        avatarRoot.position.y = THREE.MathUtils.damp(
          avatarRoot.position.y,
          reduceMotion ? 0 : Math.sin(seconds * 0.72) * 0.012,
          3.5,
          delta
        )
      }

      composer.render()
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
      bodyMaterial.dispose()
      eyeMaterial.dispose()
      composer.dispose()
      renderer.renderLists.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
      renderer.domElement.remove()
    }
  }, [reduceMotion])

  const normalizedAudioLevel = Math.min(1, Math.max(0, audioLevel || 0))
  const portraitScale = reduceMotion ? 1 : 1 + normalizedAudioLevel * (isSpeaking ? 0.045 : 0.02)

  return (
    <motion.button
      type="button"
      className={`relative flex shrink-0 cursor-pointer select-none items-center justify-center border-0 bg-transparent p-0 focus-visible:outline-none ${
        compact
          ? 'h-24 w-24 sm:h-28 sm:w-28'
          : 'h-56 w-56 sm:h-64 sm:w-64 md:h-80 md:w-80'
      }`}
      animate={{ scale: portraitScale }}
      transition={{ type: 'spring', stiffness: 280, damping: 20, mass: 0.7 }}
      whileHover={reduceMotion ? undefined : { scale: portraitScale * 1.035 }}
      whileTap={reduceMotion ? undefined : { scale: portraitScale * 0.96 }}
      onClick={onClick}
      title="Clique para alternar escuta de voz da Gideon"
      aria-label="Alternar escuta de voz da Gideon"
      aria-pressed={isListening}
    >
      <span className="relative h-full w-full overflow-visible">
        <span
          ref={viewportRef}
          className={`avatar-viewport absolute inset-0 ${compact ? 'compact' : ''}`}
          aria-hidden="true"
        />

        {renderFailed && (
          <span className="absolute inset-0 flex flex-col items-center justify-center text-cyan-200">
            <span className={compact ? 'text-2xl font-light' : 'text-5xl font-light'}>G</span>
            <span className="mt-1 font-mono text-[8px] tracking-[0.28em] opacity-70">GIDEON</span>
          </span>
        )}
      </span>
    </motion.button>
  )
}
