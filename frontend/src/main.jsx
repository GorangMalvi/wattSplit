import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import Root from './Root.jsx'
import UpdateBanner from './components/UpdateBanner.jsx'

// The Google Play build leaves the GitHub update check out entirely (Play only allows Play updates).
const Banner = import.meta.env.VITE_PLAY_STORE ? () => null : UpdateBanner

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Banner />
    <Root />
  </StrictMode>,
)
