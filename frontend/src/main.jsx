import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import Root from './Root.jsx'
import UpdateBanner from './components/UpdateBanner.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <UpdateBanner />
    <Root />
  </StrictMode>,
)
