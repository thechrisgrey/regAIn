import { useRef, useMemo } from 'react';
import { Canvas, useFrame, extend } from '@react-three/fiber';
import CustomShaderMaterial from 'three-custom-shader-material/vanilla';
import type { ReactNode } from 'react';
import * as THREE from 'three';

extend({ CustomShaderMaterial });

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type OrbState = 'idle' | 'connecting' | 'listening' | 'speaking' | 'muted';

interface AudioVisualizerProps {
  state: OrbState;
  className?: string;
}

// ---------------------------------------------------------------------------
// Per-state visual configurations
// ---------------------------------------------------------------------------

interface StateConfig {
  baseColor: [number, number, number];
  accentColor: [number, number, number];
  fresnelColor: [number, number, number];
  noiseAmplitude: number;
  noiseFrequency: number;
  noiseSpeed: number;
  fresnelPower: number;
  fresnelIntensity: number;
  emissiveStrength: number;
  pulseSpeed: number;
  pulseAmplitude: number;
  roughness: number;
  metalness: number;
  scale: number;
}

const STATE_CONFIGS: Record<OrbState, StateConfig> = {
  idle: {
    baseColor: [0.22, 0.24, 0.30],
    accentColor: [0.36, 0.38, 0.52],
    fresnelColor: [0.50, 0.52, 0.68],
    noiseAmplitude: 0.02,
    noiseFrequency: 1.2,
    noiseSpeed: 0.15,
    fresnelPower: 3.5,
    fresnelIntensity: 0.3,
    emissiveStrength: 0.05,
    pulseSpeed: 0.8,
    pulseAmplitude: 0.005,
    roughness: 0.65,
    metalness: 0.1,
    scale: 0.92,
  },
  connecting: {
    baseColor: [0.30, 0.32, 0.50],
    accentColor: [0.46, 0.48, 0.72],
    fresnelColor: [0.56, 0.58, 0.82],
    noiseAmplitude: 0.04,
    noiseFrequency: 2.0,
    noiseSpeed: 0.6,
    fresnelPower: 2.8,
    fresnelIntensity: 0.5,
    emissiveStrength: 0.15,
    pulseSpeed: 2.5,
    pulseAmplitude: 0.02,
    roughness: 0.45,
    metalness: 0.2,
    scale: 0.95,
  },
  listening: {
    baseColor: [0.30, 0.32, 0.72],
    accentColor: [0.42, 0.44, 0.85],
    fresnelColor: [0.58, 0.60, 0.95],
    noiseAmplitude: 0.035,
    noiseFrequency: 1.6,
    noiseSpeed: 0.3,
    fresnelPower: 2.5,
    fresnelIntensity: 0.6,
    emissiveStrength: 0.2,
    pulseSpeed: 1.2,
    pulseAmplitude: 0.012,
    roughness: 0.35,
    metalness: 0.3,
    scale: 1.0,
  },
  speaking: {
    baseColor: [0.36, 0.38, 0.84],
    accentColor: [0.52, 0.46, 0.95],
    fresnelColor: [0.72, 0.65, 1.0],
    noiseAmplitude: 0.08,
    noiseFrequency: 2.4,
    noiseSpeed: 0.8,
    fresnelPower: 2.0,
    fresnelIntensity: 0.85,
    emissiveStrength: 0.45,
    pulseSpeed: 3.0,
    pulseAmplitude: 0.03,
    roughness: 0.2,
    metalness: 0.45,
    scale: 1.08,
  },
  muted: {
    baseColor: [0.35, 0.28, 0.22],
    accentColor: [0.52, 0.38, 0.28],
    fresnelColor: [0.60, 0.45, 0.35],
    noiseAmplitude: 0.015,
    noiseFrequency: 1.0,
    noiseSpeed: 0.08,
    fresnelPower: 4.0,
    fresnelIntensity: 0.2,
    emissiveStrength: 0.03,
    pulseSpeed: 0.5,
    pulseAmplitude: 0.003,
    roughness: 0.7,
    metalness: 0.05,
    scale: 0.88,
  },
};

// ---------------------------------------------------------------------------
// GLSL shaders
// ---------------------------------------------------------------------------

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uNoiseAmplitude;
  uniform float uNoiseFrequency;
  uniform float uNoiseSpeed;
  uniform float uPulseSpeed;
  uniform float uPulseAmplitude;

  varying vec3 vNormalW;
  varying vec3 vPositionW;
  varying float vDisplacement;

  //
  // Simplex 3D noise (Ashima Arts)
  //
  vec4 permute(vec4 x) { return mod(((x*34.0)+1.0)*x, 289.0); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;

    i = mod(i, 289.0);
    vec4 p = permute(permute(permute(
              i.z + vec4(0.0, i1.z, i2.z, 1.0))
            + i.y + vec4(0.0, i1.y, i2.y, 1.0))
            + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    float n_ = 1.0/7.0;
    vec3  ns = n_ * D.wyz - D.xzx;

    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);

    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);

    vec4 x  = x_ * ns.x + ns.yyyy;
    vec4 y  = y_ * ns.x + ns.yyyy;
    vec4 h  = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0)*2.0 + 1.0;
    vec4 s1 = floor(b1)*2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }

  void main() {
    float t = uTime * uNoiseSpeed;
    vec3 samplePos = csm_Position * uNoiseFrequency + t;

    // Layered noise: primary shape + fine detail
    float noise = snoise(samplePos) * 0.7
                + snoise(samplePos * 2.3 + 17.0) * 0.3;

    // Gentle pulse
    float pulse = sin(uTime * uPulseSpeed) * uPulseAmplitude;

    float displacement = noise * uNoiseAmplitude + pulse;
    vDisplacement = displacement;

    csm_Position += csm_Normal * displacement;

    vNormalW = normalize((modelMatrix * vec4(csm_Normal, 0.0)).xyz);
    vPositionW = (modelMatrix * vec4(csm_Position, 1.0)).xyz;
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 uBaseColor;
  uniform vec3 uAccentColor;
  uniform vec3 uFresnelColor;
  uniform float uFresnelPower;
  uniform float uFresnelIntensity;
  uniform float uEmissiveStrength;
  uniform float uTime;

  varying vec3 vNormalW;
  varying vec3 vPositionW;
  varying float vDisplacement;

  void main() {
    vec3 viewDir = normalize(cameraPosition - vPositionW);
    vec3 normal = normalize(vNormalW);

    // Fresnel rim
    float fresnel = pow(1.0 - max(dot(viewDir, normal), 0.0), uFresnelPower);
    fresnel *= uFresnelIntensity;

    // Mix base → accent by displacement, then add Fresnel rim
    float mixFactor = smoothstep(-0.06, 0.06, vDisplacement);
    vec3 surfaceColor = mix(uBaseColor, uAccentColor, mixFactor);
    surfaceColor = mix(surfaceColor, uFresnelColor, fresnel);

    csm_DiffuseColor = vec4(surfaceColor, 1.0);
    csm_Emissive = surfaceColor * uEmissiveStrength + uFresnelColor * fresnel * uEmissiveStrength * 2.0;
  }
`;

// ---------------------------------------------------------------------------
// Lerp helpers
// ---------------------------------------------------------------------------

function lerpScalar(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function lerpVec3(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): [number, number, number] {
  return [
    lerpScalar(a[0], b[0], t),
    lerpScalar(a[1], b[1], t),
    lerpScalar(a[2], b[2], t),
  ];
}

// ---------------------------------------------------------------------------
// Orb mesh (animated via useFrame)
// ---------------------------------------------------------------------------

function Orb({ state }: { state: OrbState }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<CustomShaderMaterial>(null);

  // Current interpolated values (mutated every frame)
  const current = useRef<StateConfig>({ ...STATE_CONFIGS[state] });

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uBaseColor: { value: new THREE.Vector3(...STATE_CONFIGS[state].baseColor) },
      uAccentColor: { value: new THREE.Vector3(...STATE_CONFIGS[state].accentColor) },
      uFresnelColor: { value: new THREE.Vector3(...STATE_CONFIGS[state].fresnelColor) },
      uNoiseAmplitude: { value: STATE_CONFIGS[state].noiseAmplitude },
      uNoiseFrequency: { value: STATE_CONFIGS[state].noiseFrequency },
      uNoiseSpeed: { value: STATE_CONFIGS[state].noiseSpeed },
      uFresnelPower: { value: STATE_CONFIGS[state].fresnelPower },
      uFresnelIntensity: { value: STATE_CONFIGS[state].fresnelIntensity },
      uEmissiveStrength: { value: STATE_CONFIGS[state].emissiveStrength },
      uPulseSpeed: { value: STATE_CONFIGS[state].pulseSpeed },
      uPulseAmplitude: { value: STATE_CONFIGS[state].pulseAmplitude },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useFrame(({ clock }) => {
    const target = STATE_CONFIGS[state];
    const c = current.current;
    const lerpFactor = 0.04; // smooth ~16-frame blend

    // Lerp all scalar values
    c.noiseAmplitude = lerpScalar(c.noiseAmplitude, target.noiseAmplitude, lerpFactor);
    c.noiseFrequency = lerpScalar(c.noiseFrequency, target.noiseFrequency, lerpFactor);
    c.noiseSpeed = lerpScalar(c.noiseSpeed, target.noiseSpeed, lerpFactor);
    c.fresnelPower = lerpScalar(c.fresnelPower, target.fresnelPower, lerpFactor);
    c.fresnelIntensity = lerpScalar(c.fresnelIntensity, target.fresnelIntensity, lerpFactor);
    c.emissiveStrength = lerpScalar(c.emissiveStrength, target.emissiveStrength, lerpFactor);
    c.pulseSpeed = lerpScalar(c.pulseSpeed, target.pulseSpeed, lerpFactor);
    c.pulseAmplitude = lerpScalar(c.pulseAmplitude, target.pulseAmplitude, lerpFactor);
    c.roughness = lerpScalar(c.roughness, target.roughness, lerpFactor);
    c.metalness = lerpScalar(c.metalness, target.metalness, lerpFactor);
    c.scale = lerpScalar(c.scale, target.scale, lerpFactor);

    // Lerp colors
    c.baseColor = lerpVec3(c.baseColor, target.baseColor, lerpFactor);
    c.accentColor = lerpVec3(c.accentColor, target.accentColor, lerpFactor);
    c.fresnelColor = lerpVec3(c.fresnelColor, target.fresnelColor, lerpFactor);

    // Push to uniforms
    const t = clock.getElapsedTime();
    uniforms.uTime.value = t;
    uniforms.uBaseColor.value.set(...c.baseColor);
    uniforms.uAccentColor.value.set(...c.accentColor);
    uniforms.uFresnelColor.value.set(...c.fresnelColor);
    uniforms.uNoiseAmplitude.value = c.noiseAmplitude;
    uniforms.uNoiseFrequency.value = c.noiseFrequency;
    uniforms.uNoiseSpeed.value = c.noiseSpeed;
    uniforms.uFresnelPower.value = c.fresnelPower;
    uniforms.uFresnelIntensity.value = c.fresnelIntensity;
    uniforms.uEmissiveStrength.value = c.emissiveStrength;
    uniforms.uPulseSpeed.value = c.pulseSpeed;
    uniforms.uPulseAmplitude.value = c.pulseAmplitude;

    // Update material properties (cast through base material type)
    const mat = materialRef.current as unknown as THREE.MeshStandardMaterial | null;
    if (mat) {
      mat.roughness = c.roughness;
      mat.metalness = c.metalness;
    }

    // Smooth scale
    const mesh = meshRef.current;
    if (mesh) {
      mesh.scale.setScalar(c.scale);
      // Slow gentle rotation
      mesh.rotation.y = t * 0.08;
      mesh.rotation.x = Math.sin(t * 0.05) * 0.1;
    }
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 64]} />
      <customShaderMaterial
        ref={materialRef}
        baseMaterial={THREE.MeshStandardMaterial}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        roughness={STATE_CONFIGS[state].roughness}
        metalness={STATE_CONFIGS[state].metalness}
        toneMapped
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Scene wrapper (lighting + environment)
// ---------------------------------------------------------------------------

function Scene({ state }: { state: OrbState }) {
  return (
    <>
      <ambientLight intensity={0.25} />
      <directionalLight position={[3, 4, 5]} intensity={0.8} color="#c8cce0" />
      <directionalLight position={[-2, -1, 3]} intensity={0.3} color="#8088b0" />
      <pointLight position={[0, 0, 3]} intensity={0.4} color="#9098d8" distance={8} />
      <Orb state={state} />
    </>
  );
}

// ---------------------------------------------------------------------------
// R3F JSX intrinsic element declaration
// ---------------------------------------------------------------------------

declare module '@react-three/fiber' {
  interface ThreeElements {
    customShaderMaterial: ThreeElements['meshStandardMaterial'] & {
      ref?: React.Ref<CustomShaderMaterial>;
      baseMaterial?: typeof THREE.MeshStandardMaterial;
      vertexShader?: string;
      fragmentShader?: string;
      uniforms?: Record<string, { value: unknown }>;
    };
  }
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export default function AudioVisualizer({ state, className }: AudioVisualizerProps): ReactNode {
  return (
    <div className={className} aria-hidden="true">
      <Canvas
        camera={{ position: [0, 0, 3], fov: 40 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        <Scene state={state} />
      </Canvas>
    </div>
  );
}
