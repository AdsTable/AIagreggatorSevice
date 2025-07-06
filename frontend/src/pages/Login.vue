<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card elevation="8">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>
              <v-icon class="mr-2">mdi-lock</v-icon>
              Sign In
            </v-toolbar-title>
          </v-toolbar>
          <v-card-text>
            <v-form ref="formRef" @submit.prevent="onLogin" :disabled="loading" v-model="valid">
              <v-text-field
                v-model="form.username"
                :rules="[v => !!v || 'Username required']"
                label="Username"
                prepend-inner-icon="mdi-account"
                autocomplete="username"
                required
                clearable
              />
              <v-text-field
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                label="Password"
                prepend-inner-icon="mdi-lock"
                :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
                @click:append-inner="showPassword = !showPassword"
                :rules="[v => !!v || 'Password required']"
                autocomplete="current-password"
                required
                clearable
              />
              <v-alert v-if="error" type="error" class="mb-2" border="start" density="compact">
                {{ error }}
              </v-alert>
              <v-btn
                :loading="loading"
                type="submit"
                color="primary"
                block
                class="mt-3"
                size="large"
              >
                Login
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
        <v-footer class="text-center mt-4" color="transparent">
          <small>© 2025 AdsTable • AI Aggregator</small>
        </v-footer>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login as loginApi } from '@/api/auth'

interface LoginForm {
  username: string
  password: string
}
const form = ref<LoginForm>({ username: '', password: '' })
const formRef = ref()
const showPassword = ref(false)
const error = ref('')
const loading = ref(false)
const valid = ref(false)
const router = useRouter()

const onLogin = async () => {
  error.value = ''
  if (!formRef.value?.validate()) return
  loading.value = true
  try {
    await loginApi(form.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.fill-height {
  min-height: 100vh;
}
</style>