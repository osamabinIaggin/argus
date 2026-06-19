import { initializeApp, type FirebaseApp } from 'firebase/app'

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId:             import.meta.env.VITE_FIREBASE_APP_ID,
}

// Only initialize if config is present — allows the app to run without Firebase
export const app: FirebaseApp | null = firebaseConfig.apiKey
  ? initializeApp(firebaseConfig)
  : null

export const VAPID_KEY: string = import.meta.env.VITE_FIREBASE_VAPID_KEY ?? ''

export const FCM_CONFIGURED = Boolean(firebaseConfig.apiKey && VAPID_KEY)
