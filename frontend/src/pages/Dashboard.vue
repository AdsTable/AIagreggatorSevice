<template>
  <div>
    <h1>Dashboard</h1>
    <div v-if="loading">
      <span>Loading...</span>
    </div>
    <div v-else-if="error" class="error">
      {{ error }}
    </div>
    <div v-else>
      <div>Status: <strong>{{ data.status }}</strong></div>
      <pre>{{ data.summary }}</pre>
      <AnalyticsChart v-if="data.charts" :charts="data.charts" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchAnalyticsDashboard } from '@api/analytics'
import type { AnalyticsDashboard } from '@types/analytics'
import AnalyticsChart from '@components/AnalyticsChart.vue'

const loading = ref(true)
const error = ref('')
const data = ref<AnalyticsDashboard | null>(null)

onMounted(async () => {
  try {
    data.value = await fetchAnalyticsDashboard()
  } catch (e: any) {
    error.value = e.message || 'API error'
  } finally {
    loading.value = false
  }
})
</script>