import type { ReactNode } from 'react';
import type { HistoryEvent } from './api';

const paths = {
  shield: 'M12 22s7-3 7-10V5l-7-3-7 3v7c0 7 7 10 7 10Z M9 12l2 2 4-4',
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  people: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M22 21v-2a4 4 0 0 0-3-4 M16 3a4 4 0 0 1 0 8',
  history: 'M3 12a9 9 0 1 0 3-7 M3 4v5h5 M12 7v5l3 2',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 11v5 M12 7h.01',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 8a7 7 0 0 1 12-2l2 6 M4 12l2 6a7 7 0 0 0 12-2',
  activity: 'M2 12h5l3-7 4 14 3-7h5',
  database: 'M4 6a8 3 0 1 0 16 0 8 3 0 1 0-16 0Z M4 6v12a8 3 0 0 0 16 0V6 M4 12a8 3 0 0 0 16 0',
  arrow: 'M4 12h15 M13 6l6 6-6 6',
  search: 'M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Z M16 16l5 5',
  download: 'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  close: 'M6 6l12 12 M18 6 6 18',
  chevron: 'm6 9 6 6 6-6',
};

export function Icon({ name, size = 20 }: { name: keyof typeof paths; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

export function PageHeading({ title, description, children }: {
  title: string; description: string; children?: ReactNode;
}) {
  return <header className="page-heading">
    <div><h1>{title}</h1><p>{description}</p></div>
    {children}
  </header>;
}

export function RequestError({ error, retry }: { error: Error; retry: () => void }) {
  return <div className="request-error" role="alert">
    <Icon name="info" />
    <p>{error.message}</p>
    <button type="button" className="button" onClick={retry}>Réessayer</button>
  </div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty"><Icon name="info" /><p>{children}</p></div>;
}

export const kindLabels = { verification: 'Vérification d’accès', passage: 'Passage' };
export const outcomeLabels = {
  authorized: 'Autorisé', denied: 'Refusé', invalid_capture: 'Capture invalide',
  entry: 'Entrée', exit: 'Sortie',
};

const utc = new Intl.DateTimeFormat('fr-FR', {
  dateStyle: 'short', timeStyle: 'medium', timeZone: 'UTC',
});

export function EventTable({ events, compact = false }: { events: HistoryEvent[]; compact?: boolean }) {
  const label = compact ? 'Derniers événements' : 'Événements filtrés';
  return <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>
    <table aria-label={label}>
      <thead><tr>
        <th scope="col">Date et heure (UTC)</th><th scope="col">Type</th><th scope="col">Résultat</th>
        <th scope="col">Personne</th>{!compact && <><th scope="col">Session</th><th scope="col">Suivi</th></>}
      </tr></thead>
      <tbody>{events.map((event, index) =>
        <tr key={index}>
          <td className="number"><time dateTime={event.occurred_at}>{utc.format(new Date(event.occurred_at))}</time></td>
          <td>{kindLabels[event.kind]}</td>
          <td><span className={`outcome outcome--${event.outcome}`}>{outcomeLabels[event.outcome]}</span></td>
          <td>{event.user_id === null ? '—' : `n° ${event.user_id}`}</td>
          {!compact && <>
            <td className="session-id">{event.session_id ?? '—'}</td>
            <td className="number">{event.track_id ?? '—'}</td>
          </>}
        </tr>,
      )}</tbody>
    </table>
  </div>;
}

export function downloadHistory(events: HistoryEvent[]) {
  const rows = [
    ['Date UTC', 'Type', 'Résultat', 'Identifiant de personne', 'Session', 'Identifiant de suivi'],
    ...events.map(event => [
      event.occurred_at, kindLabels[event.kind], outcomeLabels[event.outcome],
      event.user_id ?? '', event.session_id ?? '', event.track_id ?? '',
    ]),
  ];
  const csv = rows.map(row => row.map(value => {
    let cell = String(value);
    if (typeof value === 'string' && /^[\s]*[=+@-]|^[\t\r\n]/.test(cell)) cell = "'" + cell;
    return '"' + cell.replaceAll('"', '""') + '"';
  }).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'smartaccess-historique.csv';
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
