self.addEventListener('install', function(event) {
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  event.waitUntil(clients.claim());
});

self.addEventListener('push', function(event) {
  if (!event.data) return;

  let data;
  try {
    data = event.data.json();
  } catch (e) {
    data = { title: 'SmartAttend', body: event.data.text() };
  }

  const options = {
    body: data.body || '',
    icon: '/static/uploads/icon.png',
    badge: '/static/uploads/badge.png',
    vibrate: [100, 50, 100],
    data: { url: data.url || '/' },
    tag: 'smartattend-' + Date.now(),
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'SmartAttend', options)
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});
