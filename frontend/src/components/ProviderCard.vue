<template>
  <div class="provider-card">
    <h3>{{ provider.name }}</h3>
    <div>Type: {{ provider.type }}</div>
    <span :class="['status', provider.status]">{{ provider.status }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  provider: {
    name: string
    type: string
    status: string
  }
}>()
</script>

<style scoped>
.provider-card {
  border: 1px solid #ccc;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}
.status.healthy {
  color: green;
}
.status.degraded {
  color: orange;
}
.status.error,
.status.failed {
  color: red;
}
</style>