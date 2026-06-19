import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import wasm from 'vite-plugin-wasm'
import topLevelAwait from 'vite-plugin-top-level-await'

/**
 * Generates public/firebase-messaging-sw.js with VITE_FIREBASE_* env vars
 * baked in at build time.  Firebase configs are not secrets — they are
 * project identifiers, and security comes from Firebase Security Rules and
 * the server-side service account.
 *
 * If no Firebase config is set (empty VITE_FIREBASE_API_KEY), the service
 * worker is written as a no-op stub so the app still works without FCM.
 */
function firebaseSwPlugin(): Plugin {
  function generate(env: Record<string, string>) {
    const apiKey            = env.VITE_FIREBASE_API_KEY            ?? ''
    const authDomain        = env.VITE_FIREBASE_AUTH_DOMAIN        ?? ''
    const projectId         = env.VITE_FIREBASE_PROJECT_ID         ?? ''
    const storageBucket     = env.VITE_FIREBASE_STORAGE_BUCKET     ?? ''
    const messagingSenderId = env.VITE_FIREBASE_MESSAGING_SENDER_ID ?? ''
    const appId             = env.VITE_FIREBASE_APP_ID             ?? ''

    if (!apiKey) {
      // No Firebase config — write a no-op stub
      return `// Firebase not configured — push notifications disabled\n`
    }

    return `importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey:            ${JSON.stringify(apiKey)},
  authDomain:        ${JSON.stringify(authDomain)},
  projectId:         ${JSON.stringify(projectId)},
  storageBucket:     ${JSON.stringify(storageBucket)},
  messagingSenderId: ${JSON.stringify(messagingSenderId)},
  appId:             ${JSON.stringify(appId)},
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title   = payload.notification?.title ?? 'Video Intelligence';
  const body    = payload.notification?.body  ?? 'Your analysis is ready.';
  const videoId = payload.data?.video_id;

  self.registration.showNotification(title, {
    body,
    icon:  '/favicon.svg',
    badge: '/favicon.svg',
    tag:    videoId ?? 'vi-notification',
    data:  { video_id: videoId },
    requireInteraction: false,
  });
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const videoId = event.notification.data?.video_id;
  const url     = videoId ? '/jobs/' + videoId : '/jobs';

  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((list) => {
        for (const client of list) {
          if ('focus' in client) {
            client.focus();
            if (client.navigate) client.navigate(url);
            return;
          }
        }
        if (clients.openWindow) return clients.openWindow(url);
      })
  );
});
`
  }

  return {
    name: 'firebase-sw',
    configResolved(config) {
      const publicDir = path.resolve(config.root, 'public')
      fs.mkdirSync(publicDir, { recursive: true })
      fs.writeFileSync(path.join(publicDir, 'firebase-messaging-sw.js'), generate(config.env))
    },
  }
}

export default defineConfig({
  plugins: [
    firebaseSwPlugin(),
    wasm(),
    topLevelAwait(),
    tailwindcss(),
    react(),
  ],
  optimizeDeps: {
    // PowerSync uses WASM — exclude from Vite's pre-bundling so it can
    // handle its own WASM loading via the wasm() plugin.
    exclude: ['@powersync/web'],
  },
  worker: {
    // PowerSync spawns a SharedWorker for the sync engine — must be ES modules.
    format: 'es',
    plugins: () => [wasm(), topLevelAwait()],
  },
  server: {
    proxy: {
      '/v1': 'http://localhost:8000',
    },
    headers: {
      // Required for SharedArrayBuffer (used by the PowerSync WASM SQLite worker)
      'Cross-Origin-Opener-Policy':   'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
})
