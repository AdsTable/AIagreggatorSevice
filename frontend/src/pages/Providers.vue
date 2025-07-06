<template>
  <div>
    <h1>Providers</h1>
    <div v-if="loading">
      <span>Loading...</span>
    </div>
    <div v-else>
      <ProviderCard v-for="p in providers" :key="p.name" :provider="p" />
      <div v-if="!providers.length">No providers available</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ProviderCard from '@components/ProviderCard.vue'

interface Provider {
  name: string
  type: string
  status: string
}

const loading = ref(true)
const providers = ref<Provider[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const res = await fetch('/api/providers')
    const data = await res.json()
    providers.value = data.providers ?? []
  } finally {
    loading.value = false
  }
})
</script>