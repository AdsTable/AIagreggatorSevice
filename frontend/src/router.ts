import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from '@pages/Dashboard.vue'
import Providers from '@pages/Providers.vue'
import Analytics from '@pages/Analytics.vue'
import Diagnostics from '@pages/Diagnostics.vue'
import NotFound from '@pages/NotFound.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/providers', component: Providers },
  { path: '/analytics', component: Analytics },
  { path: '/diagnostics', component: Diagnostics },
  { path: '/:pathMatch(.*)*', component: NotFound }
]

export const router = createRouter({
  history: createWebHistory(),
  routes
})