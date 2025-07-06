import { render, fireEvent, waitFor, screen } from '@testing-library/vue'
import Login from './Login.vue'
import { vi } from 'vitest'
import { login as loginApi } from '@/api/auth'
import { createRouter, createWebHistory } from 'vue-router'

vi.mock('@/api/auth', () => ({
  login: vi.fn()
}))

const routes = [{ path: '/', component: { template: '<div>Home</div>' } }]
const router = createRouter({ history: createWebHistory(), routes })

describe('Login.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders login form and validates fields', async () => {
    render(Login, { global: { plugins: [router] } })
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument()

    // Try submit with empty fields
    await fireEvent.click(screen.getByRole('button', { name: /login/i }))
    expect(screen.getByText(/username required/i)).toBeInTheDocument()
    expect(screen.getByText(/password required/i)).toBeInTheDocument()
  })

  it('shows error on API failure', async () => {
    (loginApi as any).mockRejectedValueOnce({ response: { data: { detail: 'Invalid credentials' } } })
    render(Login, { global: { plugins: [router] } })

    await fireEvent.update(screen.getByLabelText(/username/i), 'test')
    await fireEvent.update(screen.getByLabelText(/password/i), 'wrong')
    await fireEvent.click(screen.getByRole('button', { name: /login/i }))
    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument()
    })
  })

  it('redirects on successful login', async () => {
    (loginApi as any).mockResolvedValueOnce({ access_token: 'token', token_type: 'bearer', user: { username: 'test' } })
    render(Login, { global: { plugins: [router] } })

    await fireEvent.update(screen.getByLabelText(/username/i), 'admin')
    await fireEvent.update(screen.getByLabelText(/password/i), 'correct')
    await fireEvent.click(screen.getByRole('button', { name: /login/i }))
    await waitFor(() => {
      expect(router.currentRoute.value.path).toBe('/')
    })
  })
})