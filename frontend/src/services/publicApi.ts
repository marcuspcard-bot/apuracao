import axios from 'axios'

export const publicApiUrl = (
  import.meta.env.VITE_PUBLIC_API_URL || import.meta.env.VITE_API_URL
)?.replace(/\/$/, '')

export const publicApi = axios.create({
  baseURL: publicApiUrl,
  timeout: 15000,
})

publicApi.interceptors.request.use((config) => {
  if (!publicApiUrl) throw new Error('O endereço da API não foi configurado.')
  return config
})
