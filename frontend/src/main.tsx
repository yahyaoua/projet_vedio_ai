import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { About, Dashboard, History, People } from './pages';
import { AccessPage } from './FacePages';
import { Icon } from './ui';
import './styles.css';

const pages = {
  'tableau-de-bord': { title: 'Tableau de bord', icon: 'dashboard' },
  personnes: { title: 'Personnes', icon: 'people' },
  'verifier-un-acces': { title: 'Vérifier un accès', icon: 'shield' },
  historique: { title: 'Historique', icon: 'history' },
  'a-propos': { title: 'À propos', icon: 'info' },
} as const;

type Page = keyof typeof pages;

function currentPage(hash: string): Page {
  const route = hash.slice(1).split('?', 1)[0];
  return Object.hasOwn(pages, route) ? route as Page : 'tableau-de-bord';
}

function App() {
  const [hash, setHash] = useState(() => window.location.hash);
  const [menuOpen, setMenuOpen] = useState(false);
  const [historyVisited, setHistoryVisited] = useState(() => currentPage(window.location.hash) === 'historique');
  const [historyRevision, setHistoryRevision] = useState(0);
  const page = currentPage(hash);
  const { title } = pages[page];
  const initialPerson = Number(new URLSearchParams(hash.split('?', 2)[1]).get('personne'));
  useEffect(() => {
    const onNavigation = () => {
      const next = window.location.hash;
      setHash(next);
      if (currentPage(next) === 'historique') {
        setHistoryVisited(true);
        setHistoryRevision(value => value + 1);
      }
      setMenuOpen(false);
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onNavigation);
    return () => window.removeEventListener('hashchange', onNavigation);
  }, []);
  useEffect(() => { document.title = `${title} | SmartAccess`; }, [title]);

  return <div className="shell">
    <a className="skip-link" href="#contenu" onClick={event => {
      event.preventDefault();
      document.getElementById('contenu')?.focus();
    }}>Aller au contenu</a>
    <aside className="sidebar">
      <div className="sidebar-heading">
        <a className="brand" href="#tableau-de-bord" onClick={() => setMenuOpen(false)}>
          <span className="brand-icon"><Icon name="shield" size={23} /></span>
          <span>Smart<span className="brand-accent">Access</span><small>Supervision locale</small></span>
        </a>
        <button className="button menu-toggle" type="button" aria-expanded={menuOpen}
          aria-controls="navigation" onClick={() => setMenuOpen(open => !open)}>
          <Icon name={menuOpen ? 'close' : 'menu'} size={18} /> {menuOpen ? 'Fermer' : 'Menu'}
        </button>
      </div>
      <nav id="navigation" className={menuOpen ? 'navigation is-open' : 'navigation'} aria-label="Navigation principale">
        {Object.entries(pages).map(([key, item]) =>
          <a key={key} href={`#${key}`} aria-current={page === key ? 'page' : undefined}
            onClick={() => {
              if (menuOpen) {
                setMenuOpen(false);
                document.getElementById('contenu')?.focus({ preventScroll: true });
              }
            }}>
            <Icon name={item.icon} size={18} /> {item.title}
          </a>,
        )}
      </nav>
    </aside>
    <div className="workspace">
      <div className="topbar">
        <span>SmartAccess <span className="breadcrumb-divider" aria-hidden="true">/</span> <strong>{title}</strong></span>
        <span className="mode"><Icon name="shield" size={16} /> Mode local</span>
      </div>
      <main id="contenu" className="content" tabIndex={-1}>
        {page === 'tableau-de-bord' && <Dashboard />}
        {page === 'personnes' && <People key={hash} initialPerson={initialPerson} />}
        {page === 'verifier-un-acces' && <AccessPage key={hash} initialPerson={initialPerson}
          onAttempt={() => setHistoryRevision(value => value + 1)} />}
        {page === 'a-propos' && <About />}
        {historyVisited && <div className="history-view" hidden={page !== 'historique'}>
          <History revision={historyRevision} />
        </div>}
      </main>
    </div>
  </div>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
