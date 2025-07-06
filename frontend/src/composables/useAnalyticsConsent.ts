import { ref } from 'vue'

const CONSENT_KEY = 'analytics_consent'

export function useAnalyticsConsent() {
  const showConsentBanner = ref(localStorage.getItem(CONSENT_KEY) === null)

  function acceptConsent() {
    localStorage.setItem(CONSENT_KEY, 'granted')
    showConsentBanner.value = false
    initAnalytics() // ← инициализировать аналитику только теперь
  }

  function declineConsent() {
    localStorage.setItem(CONSENT_KEY, 'declined')
    showConsentBanner.value = false
  }

  function initAnalytics() {
    // Подключение аналитики, например, Google Analytics, Plausible и т.д.
    // Например:
    // window.plausible = ...
    // или dynamic import(...)
  }

  // Если согласие уже дано — инициализировать аналитику на старте
  if (localStorage.getItem(CONSENT_KEY) === 'granted') {
    initAnalytics()
  }

  return { showConsentBanner, acceptConsent, declineConsent }
}