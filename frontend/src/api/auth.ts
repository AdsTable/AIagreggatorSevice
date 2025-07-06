import axios from 'axios'
import type { LoginForm, AuthResponse } from '@types/auth'

export async function login(form: LoginForm): Promise<AuthResponse> {
  const res = await axios.post<AuthResponse>('/api/auth/login', form)
  // Можно обработать токен, сохранить в localStorage, если надо
  return res.data
}