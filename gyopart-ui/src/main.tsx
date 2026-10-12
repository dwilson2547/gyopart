import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from './App.tsx'
import { GarageProvider } from './state/garage'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <GarageProvider>
        <App />
      </GarageProvider>
    </BrowserRouter>
  </StrictMode>,
)
