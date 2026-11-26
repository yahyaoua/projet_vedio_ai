import { useEffect, useRef, useState } from 'react';

export function useAction() {
  const active = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => () => active.current?.abort(), []);

  async function run<T>(action: (signal: AbortSignal) => Promise<T>, done: (value: T) => void) {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError('');
    try {
      const value = await action(controller.signal);
      if (!controller.signal.aborted) done(value);
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error ? failure.message : 'L’action a échoué. Réessayez.');
      }
    } finally {
      active.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return { busy, error, run, clear: () => setError('') };
}
