import { useCallback, useState } from 'react';
import { getFaceStatus, getPeople, saveFace, verifyAccess } from './api';
import type { AccessResult, FaceStatus, Person } from './api';
import { CameraCapture } from './CameraCapture';
import type { CapturedPhoto } from './CameraCapture';
import { Empty, PageHeading, RequestError } from './ui';
import { useAction } from './useAction';
import { useRequest } from './useRequest';

function useFaceStatus(id: number) {
  return useRequest(useCallback((signal: AbortSignal) => getFaceStatus(id, signal), [id]));
}

export function EnrollmentPanel({ person }: { person: Person }) {
  const { state, refresh } = useFaceStatus(person.id);
  return <section className="card workflow">
    <h2>{person.name} · n° {person.id}</h2>
    {state.status === 'loading' && <p role="status">Chargement du statut de la référence…</p>}
    {state.status === 'error' && <RequestError error={state.error} retry={refresh} />}
    {state.status === 'success' && <Enrollment person={person} initialStatus={state.data} />}
  </section>;
}

function Enrollment({ person, initialStatus }: { person: Person; initialStatus: FaceStatus }) {
  const [status, setStatus] = useState(initialStatus);
  const [editing, setEditing] = useState(!initialStatus.has_reference);
  const [shots, setShots] = useState<{ blob: Blob; digest: string }[]>([]);
  const [confirmation, setConfirmation] = useState(false);
  const action = useAction();
  const complete = shots.length === status.captures_required;

  function accept(photo: CapturedPhoto) {
    void action.run(async () => {
      const digest = await crypto.subtle.digest('SHA-256', await photo.blob.arrayBuffer());
      const key = Array.from(new Uint8Array(digest)).join(',');
      if (shots.some(shot => shot.digest === key)) throw new Error('Cette image a déjà été retenue. Reprenez la photo.');
      return { blob: photo.blob, digest: key };
    }, shot => setShots(current => [...current, shot]));
  }

  return <>
    <p>{status.has_reference ? 'Référence faciale enregistrée' : 'Visage à enregistrer'}</p>
    {confirmation && <p className="workflow-success" role="status">La référence faciale a été enregistrée.</p>}
    {editing ? <>
      <p>Avec l’accord de la personne, cadrez un seul visage bien éclairé.</p>
      {status.has_reference && <p>La référence actuelle sera remplacée après validation de toutes les nouvelles photos.</p>}
      <div className="capture-progress">
        <progress aria-label="Captures retenues" value={shots.length} max={status.captures_required} />
        <span>{shots.length} sur {status.captures_required} captures retenues</span>
      </div>
      {!complete && <CameraCapture key={shots.length} busy={action.busy}>
        {photo => <button type="button" className="button button-primary"
          disabled={action.busy || photo.analysis?.quality !== 'usable'} onClick={() => accept(photo)}>
          Retenir cette photo
        </button>}
      </CameraCapture>}
      {action.error && <p className="form-error" role="alert">{action.error}</p>}
      <div className="form-actions">
        {complete && <button type="button" className="button button-primary" disabled={action.busy} onClick={() => {
          void action.run(signal => saveFace(person.id, shots.map(shot => shot.blob), status.has_reference, signal), next => {
            setStatus(next);
            setShots([]);
            setEditing(false);
            setConfirmation(true);
          });
        }}>{action.busy ? 'Enregistrement…' : 'Enregistrer la référence'}</button>}
        {shots.length > 0 && <button type="button" className="button" disabled={action.busy} onClick={() => {
          action.clear(); setShots(current => current.slice(0, -1));
        }}>Retirer la dernière capture</button>}
        <button type="button" className="button" disabled={action.busy} onClick={() => {
          action.clear(); setEditing(false); setShots([]);
        }}>Annuler les captures</button>
      </div>
    </> : <div className="form-actions">
      {status.has_reference && <a className="button button-primary" href={`#verifier-un-acces?personne=${person.id}`}>
        Vérifier un accès
      </a>}
      <button type="button" className="button" onClick={() => {
        setConfirmation(false); setEditing(true);
      }}>{status.has_reference ? 'Réenregistrer le visage' : 'Enregistrer le visage'}</button>
    </div>}
  </>;
}

export function AccessPage({ initialPerson, onAttempt }: { initialPerson: number; onAttempt: () => void }) {
  const { state, refresh } = useRequest(getPeople);
  const [selected, setSelected] = useState(initialPerson);
  const person = state.status === 'success' ? state.data.find(item => item.id === selected) : undefined;
  return <>
    <PageHeading title="Vérifier un accès" description="Comparez une photo au visage enregistré pour le compte sélectionné." />
    <section className="card workflow">
      <h2>Choisir une personne</h2>
      {state.status === 'loading' && <p role="status">Chargement des comptes…</p>}
      {state.status === 'error' && <RequestError error={state.error} retry={refresh} />}
      {state.status === 'success' && (state.data.length ? <label className="workflow-field">
        Personne
        <select value={person?.id ?? ''} onChange={event => setSelected(Number(event.target.value))}>
          <option value="">Sélectionnez un compte</option>
          {state.data.map(item => <option key={item.id} value={item.id}>{item.name} · n° {item.id}</option>)}
        </select>
      </label> : <Empty>Créez une personne et enregistrez son visage pour commencer.</Empty>)}
    </section>
    {person && <AccessWorkflow key={person.id} person={person} onAttempt={onAttempt} />}
  </>;
}

const resultLabels = {
  authorized: 'Accès autorisé — simulation',
  denied: 'Accès refusé',
  invalid_capture: 'Photo à reprendre',
};

function AccessWorkflow({ person, onAttempt }: { person: Person; onAttempt: () => void }) {
  const { state, refresh } = useFaceStatus(person.id);
  const [result, setResult] = useState<AccessResult>();
  const action = useAction();
  return <section className="card workflow">
    <h2>Vérification de {person.name} · n° {person.id}</h2>
    {state.status === 'loading' && <p role="status">Contrôle de la référence…</p>}
    {state.status === 'error' && <RequestError error={state.error} retry={refresh} />}
    {state.status === 'success' && !state.data.has_reference && <>
      <p>Le visage de cette personne doit être enregistré avant toute vérification.</p>
      <a className="button" href={`#personnes?personne=${person.id}`}>Ouvrir ce compte dans Personnes</a>
    </>}
    {state.status === 'success' && state.data.has_reference && <>
      <p>Une photo ou une vidéo présentée à la caméra peut tromper le système.</p>
      {result ? <>
        <div role="status"><strong className={`outcome outcome--${result.outcome}`}>{resultLabels[result.outcome]}</strong></div>
        {result.outcome === 'invalid_capture' && <p>{result.capture_error ?? 'Reprenez une photo avec un seul visage bien éclairé.'}</p>}
        <details className="verification-details">
          <summary>Détails</summary>
          <p>Score de similarité cosinus · {result.similarity?.toLocaleString('fr-FR', { maximumFractionDigits: 6 }) ?? '—'}</p>
          <p>Seuil configuré · {result.threshold?.toLocaleString('fr-FR', { maximumFractionDigits: 6 }) ?? '—'}</p>
          <p>Interprétez le score sur l’échelle de similarité de −1 à 1, sans conversion en probabilité.</p>
        </details>
        <div className="form-actions">
          <button type="button" className="button button-primary" onClick={() => setResult(undefined)}>Nouvelle vérification</button>
          <a href="#historique" className="button">Voir l’historique</a>
        </div>
      </> : <>
        <CameraCapture busy={action.busy}>{photo =>
          <button type="button" className="button button-primary" disabled={action.busy} onClick={() => {
            void action.run(signal => verifyAccess(person.id, photo.blob, photo.id, signal), value => {
              setResult(value);
              onAttempt();
            });
          }}>{action.busy ? 'Vérification…' : 'Vérifier l’accès'}</button>
        }</CameraCapture>
        {action.error && <p className="form-error" role="alert">{action.error}</p>}
      </>}
    </>}
  </section>;
}
