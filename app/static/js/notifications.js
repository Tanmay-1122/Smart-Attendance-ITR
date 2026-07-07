// SmartAttend Push Notifications Client

const PUSH_KEY = '{{ vapid_public_key | default("") }}';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function subscribeToPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.log('[Push] Push notifications not supported');
    return;
  }

  if (!PUSH_KEY) {
    console.log('[Push] No VAPID key configured');
    return;
  }

  try {
    const registration = await navigator.serviceWorker.ready;

    // Check existing subscription
    let subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      // Already subscribed, just make sure server knows
      await sendSubscriptionToServer(subscription);
      return subscription;
    }

    // Request notification permission
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.log('[Push] Notification permission denied');
      return null;
    }

    // Subscribe
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(PUSH_KEY),
    });

    await sendSubscriptionToServer(subscription);
    console.log('[Push] Subscribed successfully');
    return subscription;
  } catch (e) {
    console.error('[Push] Subscription failed:', e);
    return null;
  }
}

async function unsubscribeFromPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await sendUnsubscribeToServer(subscription.endpoint);
      await subscription.unsubscribe();
      console.log('[Push] Unsubscribed');
    }
  } catch (e) {
    console.error('[Push] Unsubscribe failed:', e);
  }
}

async function sendSubscriptionToServer(subscription) {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  try {
    await fetch('/notifications/subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify(subscription.toJSON()),
    });
  } catch (e) {
    console.error('[Push] Failed to send subscription:', e);
  }
}

async function sendUnsubscribeToServer(endpoint) {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  try {
    await fetch('/notifications/unsubscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({ endpoint }),
    });
  } catch (e) {
    console.error('[Push] Failed to send unsubscribe:', e);
  }
}

// Auto-subscribe if user is logged in and notifications are enabled
document.addEventListener('DOMContentLoaded', function() {
  if (document.querySelector('meta[name="csrf-token"]') && PUSH_KEY) {
    subscribeToPush();
  }
});
