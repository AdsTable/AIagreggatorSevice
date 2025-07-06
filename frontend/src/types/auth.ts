export interface LoginForm {
  username: string
  password: string
}
export interface AuthResponse {
  access_token: string
  token_type: string
  user: { username: string }
}