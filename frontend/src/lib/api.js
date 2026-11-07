const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(
  /\/$/,
  '',
)

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options)

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`)
  }

  return response.json()
}

export function getHealth() {
  return apiRequest('/health')
}
