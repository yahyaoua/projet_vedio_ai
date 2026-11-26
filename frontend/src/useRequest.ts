import { useEffect, useState } from 'react';

type RequestState<T> =
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

export function useRequest<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<RequestState<T>>({ status: 'loading' });
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(
      data => { if (!controller.signal.aborted) setState({ status: 'success', data }); },
      error => { if (!controller.signal.aborted) setState({ status: 'error', error }); },
    );
    return () => controller.abort();
  }, [load, revision]);

  function refresh() {
    setState({ status: 'loading' });
    setRevision(current => current + 1);
  }

  return { state, refresh };
}
