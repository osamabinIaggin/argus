# Video Intelligence — Landing V2 (Angus Emmerson Style)

Portfolio-style landing inspired by [angusemmerson.com](https://angusemmerson.com), built by Thomas Monavon & Grégory Lallé.

## Tech Stack

- **React Three Fiber** — WebGL video planes with custom shaders
- **GSAP** — Loading animation, timeline, transitions
- **Lenis** — Smooth scrolling
- **Three.js** — Deformation shader (vertex displacement on planes)

## Features

- **Loading screen** — 0–100% counter with GSAP
- **WebGL video grid** — Videos rendered as textures on 3D planes
- **Deformation effect** — Vertex displacement based on distance from UV center (organic feel)
- **Hover-to-play** — Video plays on hover, pauses on leave
- **Timeline** — Synced with hovered video, clickable to seek
- **Minimal palette** — #1E1E1E (near-black) and #FFFFFF (white)

## Development

```bash
npm install
npm run dev
```

Runs at http://localhost:5175

## Video Sources

Sample videos use Google's test bucket. Replace with your own in `src/data/projects.ts`:

```ts
export const PROJECTS: Project[] = [
  { id: '1', title: 'RAG for Video', date: '2025', videoSrc: 'https://...' },
  // ...
]
```

## Build

```bash
npm run build
npm run preview
```
