import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

import { ScenariosProvider } from './contexts/ScenariosContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ScenariosProvider>
      <App />
    </ScenariosProvider>
  </StrictMode>,
)
