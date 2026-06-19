importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey:            "AIzaSyCAnr4PH4S29VTds3SoHQ780m172DM9UiE",
  authDomain:        "video-intelligence-489521.firebaseapp.com",
  projectId:         "video-intelligence-489521",
  storageBucket:     "video-intelligence-489521.firebasestorage.app",
  messagingSenderId: "543238881953",
  appId:             "1:543238881953:web:cdf086be6a0b756a5926e0",
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
