import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Canvas } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import * as THREE from 'three'
import { useMouse } from '../context/MouseContext'

const MOUSE_INFLUENCE = 0.5
const LERP_FACTOR = 0.06

function CameraRig() {
  const { camera } = useThree()
  const mouseRef = useMouse()
  const currentRef = useRef({ x: 0, y: 0 })

  useFrame(() => {
    const { x: px, y: py } = mouseRef.current
    currentRef.current.x += (px * MOUSE_INFLUENCE - currentRef.current.x) * LERP_FACTOR
    currentRef.current.y += (py * MOUSE_INFLUENCE - currentRef.current.y) * LERP_FACTOR
    camera.position.x = currentRef.current.x * 1.8
    camera.position.y = currentRef.current.y * 1.2
    camera.lookAt(0, 0, 0)
    camera.updateProjectionMatrix()
  })

  return null
}

function FloatingOrb() {
  const meshRef = useRef<THREE.Mesh>(null)
  const mouseRef = useMouse()
  const smoothRef = useRef({ x: 0, y: 0 })

  useFrame((state) => {
    if (meshRef.current) {
      smoothRef.current.x += (mouseRef.current.x * 0.4 - smoothRef.current.x) * 0.08
      smoothRef.current.y += (mouseRef.current.y * 0.4 - smoothRef.current.y) * 0.08
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.15 + smoothRef.current.x
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.2) * 0.1 + smoothRef.current.y * 0.5
    }
  })

  return (
    <Float speed={2} floatIntensity={0.5}>
      <mesh ref={meshRef} scale={1.2}>
        <icosahedronGeometry args={[2, 1]} />
        <meshStandardMaterial
          color="#DA7756"
          emissive="#DA7756"
          emissiveIntensity={0.4}
          transparent
          opacity={0.7}
        />
      </mesh>
    </Float>
  )
}

function GradientSphere() {
  const meshRef = useRef<THREE.Mesh>(null)
  const mouseRef = useMouse()

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.08 + mouseRef.current.x * 0.25
      meshRef.current.position.x = 3 + mouseRef.current.x * 1
      meshRef.current.position.y = 1 + mouseRef.current.y * 0.6
    }
  })

  return (
    <Float speed={1.5} floatIntensity={0.3} rotationIntensity={0.2}>
      <mesh ref={meshRef} position={[3, 1, -4]} scale={0.8}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial
          color="#22c55e"
          transparent
          opacity={0.2}
        />
      </mesh>
    </Float>
  )
}

function PurpleOrb() {
  const meshRef = useRef<THREE.Mesh>(null)
  const mouseRef = useMouse()

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.06 - mouseRef.current.x * 0.2
      meshRef.current.position.x = -2.5 - mouseRef.current.x * 0.8
      meshRef.current.position.y = -0.5 + mouseRef.current.y * 0.5
    }
  })

  return (
    <Float speed={2} floatIntensity={0.4}>
      <mesh ref={meshRef} position={[-2.5, -0.5, -5]} scale={0.6}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial
          color="#a78bfa"
          transparent
          opacity={0.18}
        />
      </mesh>
    </Float>
  )
}

function SceneContent() {
  return (
    <>
      <CameraRig />
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={1} color="#e89070" />
      <pointLight position={[-10, -10, 5]} intensity={0.5} color="#a78bfa" />
      <FloatingOrb />
      <GradientSphere />
      <PurpleOrb />
    </>
  )
}

export function Scene3D() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-b from-bg via-bg to-bg/95" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(218,119,86,0.15),transparent)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_40%_at_80%_20%,rgba(34,197,94,0.08),transparent)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_30%_at_20%_80%,rgba(167,139,250,0.08),transparent)]" />
      <Canvas
        camera={{ position: [0, 0, 6], fov: 50 }}
        dpr={[1, 1.5]}
        gl={{ alpha: true, antialias: true }}
        className="absolute inset-0"
      >
        <SceneContent />
      </Canvas>
    </div>
  )
}
