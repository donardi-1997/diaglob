import * as Sentry from '@sentry/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { I18nextProvider } from 'react-i18next'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import i18n from './i18n'
import { initializeFrontendObservability } from './observability'
import './index.css'
import './conversations-layout-fix.css'

initializeFrontendObservability(import.meta.env, (options) => Sentry.init(options))

const errorFallback = (
  <main role="alert">
    <h1>Algo salió mal</h1>
    <p>No pudimos mostrar Diaglob correctamente.</p>
    <button type="button" onClick={() => window.location.reload()}>
      Recargar aplicación
    </button>
  </main>
)

createRoot(document.getElementById('root')!).render(
  <Sentry.ErrorBoundary fallback={errorFallback}>
    <StrictMode>
      <I18nextProvider i18n={i18n}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </I18nextProvider>
    </StrictMode>
  </Sentry.ErrorBoundary>,
)
