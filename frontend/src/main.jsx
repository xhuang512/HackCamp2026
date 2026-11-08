import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import { applyTheme, readTheme } from './lib/theme.js'
import App from './App.jsx'
import { AuthProvider } from './lib/auth.jsx'

/* AuthProvider sits outside the router because Auth0 handles its redirect
   callback on whatever URL the student came back to, before any route
   matches. Inside the router it would remount on the first navigation and
   lose that callback. */

/* index.html already set data-theme before first paint. This re-applies the
   same value so colorScheme and the theme-color meta are set by the one
   function that owns them, rather than being half the inline script's job. */
applyTheme(readTheme())

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
