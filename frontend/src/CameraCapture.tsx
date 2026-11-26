import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { analyzeFace } from './api';
import type { FaceAnalysis } from './api';

type CameraStatus = 'stopped' | 'opening' | 'active' | 'error';
const statusLabels: Record<CameraStatus, string> = {
  stopped: 'Caméra arrêtée', opening: 'Ouverture de la caméra…',
  active: 'Caméra active', error: 'Erreur de caméra',
};

const configuredFps = Number(import.meta.env.VITE_FACE_PREVIEW_FPS || 3);
const previewInterval = 1000 / (Number.isFinite(configuredFps) ? Math.min(4, Math.max(1, configuredFps)) : 3);

export interface CapturedPhoto {
  blob: Blob;
  id: string;
  width: number;
  height: number;
  analysis?: FaceAnalysis;
  error?: string;
}

function cameraError(error: unknown) {
  const name = error instanceof DOMException ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Permission caméra refusée. Autorisez la caméra dans le navigateur, puis réessayez.';
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return 'Aucune caméra disponible. Vérifiez la connexion de votre caméra.';
  }
  if (name === 'NotReadableError' || name === 'AbortError') {
    return 'La caméra est peut-être déjà utilisée. Fermez Streamlit ou les autres applications caméra, puis réessayez.';
  }
  return 'La caméra ne fournit pas d’image. Vérifiez le périphérique, puis réessayez.';
}

function frameFrom(video: HTMLVideoElement, maximum: number) {
  if (!video.videoWidth || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    throw new Error('Attendez que la caméra affiche une image.');
  }
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, maximum / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Le navigateur ne peut pas préparer l’image.');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas;
}

function encode(canvas: HTMLCanvasElement, quality: number) {
  return new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => {
    if (blob) resolve(blob);
    else reject(new Error('La photo n’a pas pu être créée.'));
  }, 'image/jpeg', quality));
}

function FaceBoxes({ analysis }: { analysis?: FaceAnalysis }) {
  if (!analysis?.boxes.length) return null;
  return <svg className={`face-boxes ${analysis.quality === 'usable' ? 'usable' : ''}`}
    viewBox={`0 0 ${analysis.width} ${analysis.height}`} preserveAspectRatio="none" aria-hidden="true">
    {analysis.boxes.map(([left, top, right, bottom], index) =>
      <rect key={index} x={left} y={top} width={Math.max(0, right - left)}
        height={Math.max(0, bottom - top)} vectorEffect="non-scaling-stroke" />,
    )}
  </svg>;
}

export function CameraCapture({ busy = false, children }: {
  busy?: boolean;
  children: (photo: CapturedPhoto) => ReactNode;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const session = useRef<AbortController | null>(null);
  const opening = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const [status, setStatus] = useState<CameraStatus>('stopped');
  const [message, setMessage] = useState('');
  const [analysis, setAnalysis] = useState<FaceAnalysis>();
  const [photo, setPhoto] = useState<CapturedPhoto>();
  const [photoUrl, setPhotoUrl] = useState('');
  const [ratio, setRatio] = useState(4 / 3);
  const [preparing, setPreparing] = useState(false);
  const [openingPending, setOpeningPending] = useState(false);

  const release = useCallback(() => {
    session.current?.abort();
    session.current = null;
    window.clearTimeout(timer.current);
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
  }, []);

  useEffect(() => {
    function closePage() {
      release();
      setStatus('stopped');
      setPreparing(false);
      setPhoto(undefined);
      setAnalysis(undefined);
      setMessage('');
    }
    window.addEventListener('pagehide', closePage);
    return () => {
      window.removeEventListener('pagehide', closePage);
      release();
    };
  }, [release]);

  const blob = photo?.blob;
  useEffect(() => {
    if (!blob) {
      setPhotoUrl('');
      return;
    }
    const url = URL.createObjectURL(blob);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  async function poll(control: AbortController) {
    const started = performance.now();
    let interval = previewInterval;
    try {
      if (video.current && video.current.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        const frame = await encode(frameFrom(video.current, 640), 0.75);
        if (control.signal.aborted) return;
        const result = await analyzeFace(frame, control.signal);
        if (!control.signal.aborted) {
          setAnalysis(result);
          setMessage('');
        }
      }
    } catch (error) {
      if (!control.signal.aborted) {
        interval = 1000;
        setAnalysis(undefined);
        setMessage(error instanceof Error ? error.message : 'L’aperçu n’a pas pu être analysé.');
      }
    } finally {
      if (!control.signal.aborted) {
        timer.current = window.setTimeout(() => void poll(control),
          Math.max(0, interval - (performance.now() - started)));
      }
    }
  }

  async function start() {
    if (opening.current || stream.current) return;
    release();
    setPhoto(undefined);
    setAnalysis(undefined);
    setMessage('');
    setPreparing(false);
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('error');
      setMessage('La caméra requiert une page locale ou une connexion HTTPS.');
      return;
    }
    const control = new AbortController();
    session.current = control;
    opening.current = true;
    setOpeningPending(true);
    setStatus('opening');
    try {
      const opened = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        audio: false,
      });
      const player = video.current;
      if (control.signal.aborted || !player) {
        opened.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = opened;
      opened.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        if (control.signal.aborted) return;
        release();
        setStatus('error');
        setAnalysis(undefined);
        setMessage('La caméra a été déconnectée. Vérifiez le périphérique, puis réessayez.');
      }, { once: true }));
      player.srcObject = opened;
      await player.play();
      if (control.signal.aborted) return;
      setStatus('active');
      void poll(control);
    } catch (error) {
      if (control.signal.aborted) return;
      release();
      setStatus('error');
      setMessage(cameraError(error));
    } finally {
      opening.current = false;
      setOpeningPending(false);
    }
  }

  async function capture() {
    if (!video.current || !stream.current) return;
    let canvas: HTMLCanvasElement;
    try {
      canvas = frameFrom(video.current, 1280);
    } catch (error) {
      setMessage((error as Error).message);
      return;
    }
    release();
    setStatus('stopped');
    setMessage('');
    setAnalysis(undefined);
    setPreparing(true);
    const control = new AbortController();
    session.current = control;
    let frozen: CapturedPhoto | undefined;
    try {
      const image = await encode(canvas, 0.92);
      if (control.signal.aborted) return;
      frozen = { blob: image, id: crypto.randomUUID(), width: canvas.width, height: canvas.height };
      setPhoto(frozen);
      const exact = await analyzeFace(image, control.signal);
      if (!control.signal.aborted) setPhoto({ ...frozen, analysis: exact });
    } catch (error) {
      if (control.signal.aborted) return;
      const detail = error instanceof Error ? error.message : 'La photo n’a pas pu être analysée.';
      if (frozen) setPhoto({ ...frozen, error: detail });
      else setMessage(detail);
    } finally {
      if (!control.signal.aborted) {
        session.current = null;
        setPreparing(false);
      }
    }
  }

  const streaming = status === 'opening' || status === 'active';
  return <div className="camera">
    <p className="camera-status" role="status">{statusLabels[status]}</p>
    {message && <p className="form-error" role="alert">{message}</p>}
    <div className="camera-viewport" hidden={!streaming} style={{ aspectRatio: ratio }}>
      <video ref={video} muted playsInline aria-label="Aperçu de la caméra"
        onResize={event => {
          const player = event.currentTarget;
          if (player.videoHeight) setRatio(player.videoWidth / player.videoHeight);
        }} />
      <FaceBoxes analysis={analysis} />
    </div>
    {streaming && <p className="camera-guidance" role="status">
      {analysis?.message ?? (status === 'active' && !message ? 'Analyse de l’aperçu…' : '')}
    </p>}
    {photo && photoUrl && <figure>
      <div className="camera-viewport" style={{ aspectRatio: photo.width / photo.height }}>
        <img src={photoUrl} alt="Photo retenue" />
        <FaceBoxes analysis={photo.analysis} />
      </div>
      <figcaption>Photo retenue {photo.analysis && `· ${photo.analysis.quality === 'usable'
        ? 'Qualité validée' : photo.analysis.message}`}</figcaption>
    </figure>}
    {preparing && <p role="status">Validation de la photo…</p>}
    {photo?.error && <p className="form-error" role="alert">{photo.error}</p>}
    <div className="form-actions">
      {!streaming && !photo && <button type="button" className="button button-primary"
        disabled={busy || preparing || openingPending} onClick={() => void start()}>Démarrer la caméra</button>}
      {status === 'active' && <button type="button" className="button button-primary"
        disabled={busy} onClick={() => void capture()}>Capturer</button>}
      {photo && <button type="button" className="button" disabled={busy || openingPending}
        onClick={() => void start()}>Reprendre</button>}
      {streaming && <button type="button" className="button" onClick={() => {
        release(); setStatus('stopped'); setAnalysis(undefined); setMessage('');
      }}>Arrêter</button>}
      {photo && !preparing && children(photo)}
    </div>
  </div>;
}
