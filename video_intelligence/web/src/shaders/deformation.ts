export const vertexShader = `
  varying vec2 vUv;
  varying float vDeform;

  uniform float uDeform;
  uniform float uTime;

  void main() {
    vUv = uv;
    float dist = length(uv - 0.5);
    vDeform = sin(dist * 3.14159) * uDeform;
    vec3 pos = position;
    pos.z += vDeform;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`

export const fragmentShader = `
  varying vec2 vUv;

  uniform sampler2D uMap;

  void main() {
    gl_FragColor = texture(uMap, vUv);
  }
`
