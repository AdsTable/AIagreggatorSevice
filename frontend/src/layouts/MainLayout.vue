<template>
  <div>
    <!-- ...Header/nav... -->
    <router-view />
    <ConsentBanner v-if="showConsentBanner" @accept="acceptConsent" @decline="declineConsent" />
    <!-- ...Footer... -->
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ConsentBanner from '@components/ConsentBanner.vue'
import { useAnalyticsConsent } from '@composables/useAnalyticsConsent'

const { showConsentBanner, acceptConsent, declineConsent } = useAnalyticsConsent()

onMounted(() => {
  // Optional: auto-init analytics here if consent already given
})
</script>