import { AdminAccess } from './components/AdminAccess'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  FileCheck2,
  FileStack,
  LayoutDashboard,
  Upload,
  Monitor,
} from 'lucide-react'
import { useEffect } from 'react'
import { Importar } from './pages/Importar'
import { Boletins } from './pages/Boletins'
import { DetalhesBoletim } from './pages/DetalhesBoletim'
import { AbrirPdf } from './pages/AbrirPdf'
import { Acompanhamento } from './pages/Acompanhamento'
import { ConfiguracaoTelao } from './pages/ConfiguracaoTelao'
import { Divulgacao } from './pages/Divulgacao'

export default function App() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  if (pathname === '/divulgacao' || pathname === '/divulgacao/')
    return <Divulgacao />
  return (
    <AdminAccess>
      <div className="app-shell">
        <a className="skip-link" href="#main">
          Ir para o conteúdo
        </a>
        <header className="app-header">
          <div className="header-inner">
            <NavLink to="/" className="brand">
              <span className="brand-icon">
                <FileCheck2 size={24} />
              </span>
              <span>
                Boletins
                <span className="brand-subtitle">REGISTRO ELEITORAL</span>
              </span>
            </NavLink>
            <nav aria-label="Navegação principal">
              <NavLink to="/acompanhamento">
                <LayoutDashboard size={17} />
                Visão geral
              </NavLink>
              <NavLink
                to="/importar"
                className={({ isActive }) =>
                  isActive || pathname === '/' ? 'active' : ''
                }
              >
                <Upload size={17} />
                Importar
              </NavLink>
              <NavLink to="/boletins">
                <FileStack size={17} />
                Boletins
              </NavLink>
              <NavLink to="/configuracao-telao">
                <Monitor size={17} />
                Telão
              </NavLink>
            </nav>
            <span className="header-label">Boletim de Urna</span>
          </div>
        </header>
        <main id="main">
          <Routes>
            <Route path="/" element={<Importar />} />
            <Route path="/acompanhamento" element={<Acompanhamento />} />
            <Route path="/configuracao-telao" element={<ConfiguracaoTelao />} />
            <Route path="/importar" element={<Importar />} />
            <Route path="/boletins" element={<Boletins />} />
            <Route path="/boletins/:id" element={<DetalhesBoletim />} />
            <Route path="/boletins/:id/pdf" element={<AbrirPdf />} />
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <h1>Página não encontrada</h1>
                  <NavLink to="/importar" className="button">
                    Voltar à importação
                  </NavLink>
                </div>
              }
            />
          </Routes>
        </main>
        <footer>
          <span>Boletins de Urna</span>
          <span>Importação e conferência</span>
        </footer>
      </div>
    </AdminAccess>
  )
}
