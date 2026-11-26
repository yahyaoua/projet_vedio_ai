interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_FACE_PREVIEW_FPS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
