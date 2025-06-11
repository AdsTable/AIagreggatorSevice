#Пример App.vue (Vue 3, Vite)
#src/App.vue

<template>
  <MainLayout>
    <router-view/>
  </MainLayout>
</template>

<script setup>
import MainLayout from './layouts/MainLayout.vue'
</script>