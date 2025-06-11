# Пример маршрутизации (Vue Router)
# scr/router.js

import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.vue'
import Providers from './pages/Providers.vue'
import Analytics from './pages/Analytics.vue'
import Diagnostics from './pages/Diagnostics.vue'
import Login from './pages/Login.vue'
import NotFound from './pages/NotFound.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/providers', component: Providers },
  { path: '/analytics', component: Analytics },
  { path: '/diagnostics', component: Diagnostics },
  { path: '/login', component: Login },
  { path: '/:pathMatch(.*)*', component: NotFound }
]

export default createRouter({
  history: createWebHistory(),
  routes
})