<template>
  <q-banner dense color="primary" class="q-mb-md" style="position: fixed; bottom: 0; left: 0; width: 100%; z-index: 1000;">
    <span>
      We use analytics cookies to improve your experience. Read our <router-link to="/privacy">Privacy Policy</router-link>.
    </span>
    <template #action>
      <q-btn label="Accept" color="white" text-color="primary" @click="$emit('accept')" flat />
      <q-btn label="Decline" color="white" text-color="primary" @click="$emit('decline')" flat />
    </template>
  </q-banner>
</template>
<script setup lang="ts">
</script>