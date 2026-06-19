import { useRef, useEffect, useState, useMemo } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { vertexShader, fragmentShader } from '../../shaders/deformation'

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

/** Corner bracket lines for hover state */
function BracketLines({
  width,
  height,
  bracketSize,
  visible,
  opacityRef,
}: {
  width: number
  height: number
  bracketSize: number
  visible: boolean
  opacityRef: React.MutableRefObject<number>
}) {
  const z = 0.02
  const geometry = useMemo(() => {
    const hw = width / 2
    const hh = height / 2
    const s = bracketSize
    const positions = new Float32Array([
      -hw, hh, z, -hw, hh - s, z, -hw, hh, z, -hw + s, hh, z,       // top-left L
      hw - s, hh, z, hw, hh, z, hw, hh, z, hw, hh - s, z,            // top-right L
      hw, -hh + s, z, hw, -hh, z, hw, -hh, z, hw - s, -hh, z,       // bottom-right L
      -hw + s, -hh, z, -hw, -hh, z, -hw, -hh, z, -hw, -hh + s, z,   // bottom-left L
    ])
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return g
  }, [width, height, bracketSize])
  const matRef = useRef<THREE.LineBasicMaterial>(null)

  useFrame(() => {
    const target = visible ? 1 : 0
    opacityRef.current += (target - opacityRef.current) * 0.15
    if (matRef.current) matRef.current.opacity = opacityRef.current
  })

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial
        ref={matRef}
        color="white"
        transparent
        opacity={0}
        depthTest={false}
      />
    </lineSegments>
  )
}

/** Horizontal gap between video slots — smaller = more videos visible */
const SLOT_GAP = 0.12

interface VideoPlaneProps {
  videoSrc: string
  index: number
  total: number
  isHovered: boolean
  deformStrength: number
  onHover?: () => void
  onLeave?: () => void
}

export function VideoPlane({ videoSrc, index, isHovered, deformStrength, onHover, onLeave }: VideoPlaneProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const textureRef = useRef<THREE.VideoTexture | null>(null)
  const bracketOpacityRef = useRef(0)
  const { viewport } = useThree()
  const [playTime, setPlayTime] = useState({ current: 0, duration: 0 })
  const [uniforms, setUniforms] = useState<{
    uMap: { value: THREE.VideoTexture | null }
    uDeform: { value: number }
    uTime: { value: number }
  } | null>(null)

  useEffect(() => {
    const video = document.createElement('video')
    video.src = videoSrc
    video.crossOrigin = 'anonymous'
    video.loop = true
    video.muted = true
    video.playsInline = true
    video.preload = 'auto'
    videoRef.current = video

    const onTimeUpdate = () => setPlayTime({ current: video.currentTime, duration: video.duration })
    const onLoadedMetadata = () => setPlayTime({ current: video.currentTime, duration: video.duration })
    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('loadedmetadata', onLoadedMetadata)

    const texture = new THREE.VideoTexture(video)
    texture.minFilter = THREE.LinearFilter
    texture.magFilter = THREE.LinearFilter
    texture.format = THREE.RGBAFormat
    textureRef.current = texture

    setUniforms({
      uMap: { value: texture },
      uDeform: { value: 0 },
      uTime: { value: 0 },
    })

    return () => {
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('loadedmetadata', onLoadedMetadata)
      video.pause()
      video.src = ''
      texture.dispose()
    }
  }, [videoSrc])

  useFrame((state) => {
    if (!meshRef.current || !uniforms) return

    const targetDeform = isHovered ? deformStrength * 1.5 : deformStrength
    uniforms.uDeform.value += (targetDeform - uniforms.uDeform.value) * 0.08
    uniforms.uTime.value = state.clock.elapsedTime
  })

  const handlePointerEnter = () => {
    if (videoRef.current) {
      videoRef.current.play().catch(() => {})
    }
    onHover?.()
  }

  const handlePointerLeave = () => {
    if (videoRef.current) {
      videoRef.current.pause()
    }
    onLeave?.()
  }

  if (!uniforms) return null

  // Plane size: ~28% of viewport width, scales with browser
  const planeWidth = viewport.width * 0.28
  const planeHeight = planeWidth * 0.6

  // Horizontal scrollable row: top, bottom, top, bottom, top...
  const slotWidth = planeWidth + viewport.width * SLOT_GAP
  const offsetX = index * slotWidth
  const topY = viewport.height * 0.15
  const bottomY = -viewport.height * 0.15
  const offsetY = index % 2 === 0 ? topY : bottomY
  const bracketSize = Math.min(planeWidth, planeHeight) * 0.12

  return (
    <group position={[offsetX, offsetY, 0]}>
      <mesh
        ref={meshRef}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
      >
        <planeGeometry args={[planeWidth, planeHeight, 32, 32]} />
        <shaderMaterial
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          uniforms={uniforms}
          side={THREE.DoubleSide}
        />
      </mesh>
      <BracketLines
        width={planeWidth}
        height={planeHeight}
        bracketSize={bracketSize}
        visible={isHovered}
        opacityRef={bracketOpacityRef}
      />
      {isHovered && (
        <Html
          position={[planeWidth / 2 - 0.15, -planeHeight / 2 + 0.15, 0.03]}
          transform
          style={{
            pointerEvents: 'none',
            fontSize: '10px',
            fontFamily: 'system-ui, sans-serif',
            color: 'rgba(255,255,255,0.7)',
            whiteSpace: 'nowrap',
          }}
        >
          {formatTime(playTime.current)}
        </Html>
      )}
    </group>
  )
}
