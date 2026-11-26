export interface Health {
  status: 'ok';
  database: 'accessible';
}

export interface Person {
  id: number;
  name: string;
}

export interface FaceStatus {
  has_reference: boolean;
  captures_required: number;
}

export interface FaceAnalysis {
  width: number;
  height: number;
  boxes: [number, number, number, number][];
  quality: 'no_face' | 'multiple' | 'too_small' | 'blurry' | 'usable';
  message: string;
}

export interface AccessResult {
  outcome: 'authorized' | 'denied' | 'invalid_capture';
  similarity: number | null;
  threshold: number | null;
  capture_error: string | null;
}

export type EventKind = 'verification' | 'passage';
export type EventOutcome = 'authorized' | 'denied' | 'invalid_capture' | 'entry' | 'exit';

export interface HistoryEvent {
  occurred_at: string;
  kind: EventKind;
  outcome: EventOutcome;
  user_id: number | null;
  session_id: string | null;
  track_id: number | null;
  similarity: number | null;
  threshold: number | null;
}

export interface HistoryFilters {
  kind?: EventKind;
  outcome?: EventOutcome;
  session?: string;
  start?: string;
  end?: string;
  limit?: number;
}

export class ApiError extends Error {
  constructor(message: string, readonly status?: number, readonly detail?: string) {
    super(message);
  }
}

const apiBase = (import.meta.env.VITE_API_BASE_URL?.trim() || '/api').replace(/\/+$/, '');

async function request<T>(path: string, signal: AbortSignal, options: RequestInit = {}): Promise<T> {
  const requestSignal = AbortSignal.any([signal, AbortSignal.timeout(10_000)]);
  try {
    const response = await fetch(apiBase + path, {
      ...options,
      signal: requestSignal,
      headers: { Accept: 'application/json', ...options.headers },
      cache: 'no-store',
    });
    const json = response.headers.get('content-type')?.includes('application/json');
    if (!response.ok) {
      const body = json ? await response.json().catch(() => null) : null;
      const detail = typeof body?.detail === 'string' ? body.detail
        : typeof body?.detail?.message === 'string' ? body.detail.message : undefined;
      const message = detail ?? (response.status === 422
        ? 'Les données envoyées sont invalides.'
        : response.status >= 500 && !json
          ? 'L’API ne répond pas. Vérifiez que FastAPI est démarré.'
          : 'La requête a échoué.');
      throw new ApiError(`${message} (HTTP ${response.status})`, response.status, detail);
    }
    if (!json) throw new ApiError('Réponse inattendue. Vérifiez l’adresse de l’API et le proxy.');
    return await response.json() as T;
  } catch (error) {
    if (signal.aborted || error instanceof ApiError) throw error;
    if (requestSignal.aborted) throw new ApiError('Le délai de réponse de l’API est dépassé.');
    if (error instanceof SyntaxError) throw new ApiError('L’API a renvoyé une réponse JSON illisible.');
    throw new ApiError('L’API est injoignable. Vérifiez que FastAPI est démarré, puis réessayez.');
  }
}

export const getHealth = (signal: AbortSignal) => request<Health>('/health', signal);
export const getPeople = (signal: AbortSignal) => request<Person[]>('/people', signal);

export function createPerson(name: string, signal: AbortSignal) {
  return request<Person>('/people', signal, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  });
}

export const getFaceStatus = (id: number, signal: AbortSignal) => request<FaceStatus>(`/people/${id}/face`, signal);

export function analyzeFace(photo: Blob, signal: AbortSignal) {
  return request<FaceAnalysis>('/faces/analyze', signal, { method: 'POST', body: photo });
}

function encodePhoto(photo: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
    reader.onerror = () => reject(new Error('La photo n’a pas pu être préparée.'));
    reader.readAsDataURL(photo);
  });
}

export async function saveFace(id: number, photos: Blob[], replace: boolean, signal: AbortSignal) {
  const encoded = await Promise.all(photos.map(encodePhoto));
  return request<FaceStatus>(`/people/${id}/face?replace=${replace}`, signal, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ photos: encoded }),
  });
}

export function verifyAccess(id: number, photo: Blob, requestId: string, signal: AbortSignal) {
  return request<AccessResult>(`/people/${id}/verify`, signal, {
    method: 'POST', headers: { 'Idempotency-Key': requestId }, body: photo,
  });
}

export function getHistory(filters: HistoryFilters, signal: AbortSignal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') query.set(key, String(value));
  }
  return request<HistoryEvent[]>(`/history?${query}`, signal);
}
