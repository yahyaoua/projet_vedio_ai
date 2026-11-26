import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, createPerson, getHealth, getHistory, getPeople } from './api';
import type { EventKind, EventOutcome, HistoryFilters } from './api';
import { Empty, EventTable, Icon, PageHeading, RequestError, downloadHistory, kindLabels, outcomeLabels } from './ui';
import { useRequest } from './useRequest';
import { useAction } from './useAction';
import { EnrollmentPanel } from './FacePages';

const loadRecent = (signal: AbortSignal) => getHistory({ limit: 5 }, signal);

export function Dashboard() {
  const health = useRequest(getHealth);
  const people = useRequest(getPeople);
  const recent = useRequest(loadRecent);
  const status = health.state;
  const connected = status.status === 'success' && status.data.status === 'ok';
  const databaseAccessible = status.status === 'success' && status.data.database === 'accessible';
  const databaseKnownDown = status.status === 'error' && status.error instanceof ApiError
    && status.error.status === 503 && status.error.detail === 'Base SmartAccess inaccessible ou non initialisée.';
  const serviceLabel = status.status === 'loading' ? 'Vérification…' : connected ? 'Opérationnel'
    : databaseKnownDown ? 'Répond avec une erreur' : 'État non confirmé';
  const databaseLabel = status.status === 'loading' ? 'Vérification…' : databaseAccessible ? 'Accessible'
    : databaseKnownDown ? 'Inaccessible' : 'État inconnu';
  const loading = [status, people.state, recent.state].some(state => state.status === 'loading');
  return <>
    <PageHeading title="Centre de supervision" description="Consultez l’état du service, les comptes et les derniers événements.">
      <button className="button button-primary" type="button" disabled={loading} onClick={() => {
        health.refresh(); people.refresh(); recent.refresh();
      }}><Icon name="refresh" size={17} /> Actualiser</button>
    </PageHeading>

    <div className="metrics">
      <section className="card metric">
        <div className="metric-label"><span className="icon-tile"><Icon name="activity" /></span><h2>État du service</h2></div>
        <strong role="status" className={connected ? 'healthy' : undefined}>{serviceLabel}</strong>
      </section>
      <section className="card metric">
        <div className="metric-label"><span className="icon-tile"><Icon name="database" /></span><h2>Accès aux données</h2></div>
        <strong role="status" className={databaseAccessible ? 'healthy' : undefined}>{databaseLabel}</strong>
      </section>
      <section className="card metric">
        <div className="metric-label"><span className="icon-tile"><Icon name="people" /></span><h2>Comptes enregistrés</h2></div>
        <strong role="status">{people.state.status === 'success' ? people.state.data.length
          : people.state.status === 'loading' ? 'Chargement…' : '—'}</strong>
        <a href="#personnes">Voir les personnes <Icon name="arrow" size={16} /></a>
      </section>
    </div>
    {status.status === 'error' && <RequestError error={status.error} retry={health.refresh} />}
    {people.state.status === 'error' && <RequestError error={people.state.error} retry={people.refresh} />}

    <section className="card">
      <div className="card-heading">
        <div><h2>Derniers événements</h2><p>Tentatives d’accès et passages, du plus récent au plus ancien.</p></div>
        <a className="button" href="#historique">Voir l’historique <Icon name="arrow" size={17} /></a>
      </div>
      {recent.state.status === 'loading' && <p className="loading" role="status">Chargement des événements…</p>}
      {recent.state.status === 'error' && <RequestError error={recent.state.error} retry={recent.refresh} />}
      {recent.state.status === 'success' && (recent.state.data.length
        ? <EventTable events={recent.state.data} compact />
        : <Empty>Aucun événement enregistré.</Empty>)}
    </section>
    <details className="card service-details">
      <summary><Icon name="info" size={17} /> Détails du service <Icon name="chevron" size={17} /></summary>
      <dl>
        <div><dt>API FastAPI</dt><dd>{serviceLabel}. État fourni par <code>/api/health</code>.</dd></div>
        <div><dt>Base SQLite</dt><dd>{databaseLabel}. Le contrôle porte sur les tables de lecture.</dd></div>
      </dl>
    </details>
  </>;
}

const normalizeSearch = (value: string) => value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('fr');

export function People({ initialPerson }: { initialPerson: number }) {
  const [search, setSearch] = useState('');
  const [name, setName] = useState('');
  const [selected, setSelected] = useState(initialPerson);
  const creation = useAction();
  const { state, refresh } = useRequest(getPeople);
  const person = state.status === 'success' ? state.data.find(item => item.id === selected) : undefined;
  const query = normalizeSearch(search.trim());
  const matches = state.status === 'success'
    ? state.data.filter(person => normalizeSearch(person.name).includes(query) || String(person.id).includes(query))
    : [];

  return <>
    <PageHeading title="Personnes" description="Créez un compte ou sélectionnez une personne pour enregistrer son visage." />
    <form className="card workflow" onSubmit={event => {
      event.preventDefault();
      void creation.run(signal => createPerson(name, signal), created => {
        setName(''); setSearch(''); setSelected(created.id); refresh();
      });
    }}>
      <h2>Créer une personne</h2>
      <div className="workflow-form">
        <label className="workflow-field">Nom ou pseudonyme
          <input required value={name} onChange={event => setName(event.target.value)} disabled={creation.busy} />
        </label>
        <button type="submit" className="button button-primary" disabled={creation.busy || !name.trim()}>
          {creation.busy ? 'Création…' : 'Créer la personne'}
        </button>
      </div>
      {creation.error && <p className="form-error" role="alert">{creation.error}</p>}
    </form>
    <section className="card">
      <div className="card-heading">
        <div><h2>Liste des comptes</h2><p>Utilisez l’identifiant pour distinguer les homonymes.</p></div>
        <label className="search">
          <span className="sr-only">Rechercher par nom ou identifiant</span>
          <Icon name="search" size={18} />
          <input type="search" placeholder="Nom ou identifiant" value={search} onChange={event => setSearch(event.target.value)} />
        </label>
      </div>
      {state.status === 'loading' && <p className="loading" role="status">Chargement des comptes…</p>}
      {state.status === 'error' && <RequestError error={state.error} retry={refresh} />}
      {state.status === 'success' && (matches.length ? <div className="table-scroll" role="region" aria-label="Liste des comptes" tabIndex={0}>
        <table aria-label="Comptes enregistrés"><thead><tr><th scope="col">Identifiant</th><th scope="col">Nom</th><th scope="col">Sélection</th></tr></thead>
          <tbody>{matches.map(person => <tr key={person.id}>
            <td className="number person-id">n° {person.id}</td><td>{person.name}</td>
            <td><button type="button" className="button" aria-pressed={selected === person.id}
              aria-label={`Sélectionner ${person.name}, n° ${person.id}`}
              onClick={() => setSelected(person.id)}>{selected === person.id ? 'Sélectionné' : 'Sélectionner'}</button></td>
          </tr>)}</tbody>
        </table>
      </div> : <Empty>{state.data.length ? 'Aucun compte ne correspond à la recherche.' : 'Aucun compte enregistré.'}</Empty>)}
    </section>
    {person && <EnrollmentPanel key={person.id} person={person} />}
  </>;
}

const initialFilters: HistoryFilters = { limit: 100 };
const allOutcomes: EventOutcome[] = ['authorized', 'denied', 'invalid_capture', 'entry', 'exit'];

export function History({ revision }: { revision: number }) {
  const [draft, setDraft] = useState(initialFilters);
  const [applied, setApplied] = useState({ filters: initialFilters, revision: 0 });
  const [validation, setValidation] = useState('');
  const outcomes = draft.kind === 'verification' ? allOutcomes.slice(0, 3)
    : draft.kind === 'passage' ? allOutcomes.slice(3) : allOutcomes;

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.start && draft.end && draft.start > draft.end) {
      setValidation('La date de début doit précéder la date de fin ou lui être égale.');
      return;
    }
    setValidation('');
    setApplied(current => ({
      filters: { ...draft, session: draft.session?.trim() || undefined },
      revision: current.revision + 1,
    }));
  }

  return <>
    <PageHeading title="Historique" description="Retrouvez les tentatives d’accès et les passages enregistrés." />
    <form className="card filters" onSubmit={apply}>
      <h2>Filtrer les événements</h2>
      <div className="filter-grid">
        <label>Type
          <select value={draft.kind ?? ''} onChange={event => {
            const kind = (event.target.value || undefined) as EventKind | undefined;
            setDraft({ ...draft, kind, outcome: undefined, session: kind === 'verification' ? undefined : draft.session });
          }}>
            <option value="">Tous les types</option>
            {Object.entries(kindLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>Résultat
          <select value={draft.outcome ?? ''} onChange={event => setDraft({ ...draft, outcome: (event.target.value || undefined) as EventOutcome | undefined })}>
            <option value="">Tous les résultats</option>
            {outcomes.map(outcome => <option key={outcome} value={outcome}>{outcomeLabels[outcome]}</option>)}
          </select>
        </label>
        <label>Session de comptage
          <input type="text" placeholder="Identifiant exact" disabled={draft.kind === 'verification'} value={draft.session ?? ''}
            onChange={event => setDraft({ ...draft, session: event.target.value })} />
        </label>
        <label>Du (UTC)<input type="date" value={draft.start ?? ''} onChange={event => setDraft({ ...draft, start: event.target.value })} /></label>
        <label>Au (UTC)<input type="date" value={draft.end ?? ''} onChange={event => setDraft({ ...draft, end: event.target.value })} /></label>
        <label>Limite
          <select value={draft.limit} onChange={event => setDraft({ ...draft, limit: Number(event.target.value) })}>
            {[25, 50, 100, 250, 500].map(limit => <option key={limit} value={limit}>{limit} événements</option>)}
          </select>
        </label>
      </div>
      {validation && <p className="form-error" role="alert">{validation}</p>}
      <div className="form-actions">
        <button className="button button-primary" type="submit">Appliquer les filtres</button>
        <button className="button" type="button" onClick={() => {
          setDraft(initialFilters); setValidation('');
          setApplied(current => ({ filters: initialFilters, revision: current.revision + 1 }));
        }}>Réinitialiser les filtres</button>
      </div>
    </form>
    <HistoryResults key={`${applied.revision}:${revision}`} filters={applied.filters} />
  </>;
}

function HistoryResults({ filters }: { filters: HistoryFilters }) {
  const load = useCallback((signal: AbortSignal) => getHistory(filters, signal), [filters]);
  const { state, refresh } = useRequest(load);
  return <section className="card">
    <div className="card-heading">
      <div><h2>Résultats</h2>
        {state.status === 'success' && <p>
          {state.data.length} événement{state.data.length === 1 ? '' : 's'} · Limite de {filters.limit}
        </p>}
      </div>
      <button className="button" type="button" disabled={state.status !== 'success' || !state.data.length}
        onClick={() => { if (state.status === 'success') downloadHistory(state.data); }}>
        <Icon name="download" size={17} /> Exporter le CSV
      </button>
    </div>
    {state.status === 'loading' && <p className="loading" role="status">Chargement de l’historique…</p>}
    {state.status === 'error' && <RequestError error={state.error} retry={refresh} />}
    {state.status === 'success' && (state.data.length
      ? <EventTable events={state.data} />
      : <Empty>Aucun événement ne correspond aux filtres appliqués.</Empty>)}
  </section>;
}

export function About() {
  return <>
    <PageHeading title="À propos" description="Périmètre de l’interface et origine du projet." />
    <section className="card about">
      <h2>Le projet SmartAccess</h2>
      <p>SmartAccess est un prototype académique inspiré du volet logiciel du CPS de la Préfecture de Rabat.</p>
      <dl>
        <div><dt>Personnes</dt><dd>Gestion des profils et enrôlement.</dd></div>
        <div><dt>Vérification faciale</dt><dd>Contrôle d’accès 1:1 avec ouverture simulée.</dd></div>
        <div><dt>Comptage des passages</dt><dd>Analyse vidéo et détection des franchissements.</dd></div>
        <div><dt>Historique</dt><dd>Consultation et export des événements.</dd></div>
      </dl>
      <p className="about-note"><Icon name="info" /> React permet l’enregistrement facial et la vérification d’accès. Le comptage vidéo reste disponible dans Streamlit.</p>
    </section>
  </>;
}
