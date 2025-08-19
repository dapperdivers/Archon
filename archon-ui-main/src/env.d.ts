/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_API_HOST?: string;
  readonly ARCHON_SERVER_PORT?: string;
  readonly ARCHON_MCP_PORT?: string;
  readonly VITE_ENABLE_WEBSOCKET?: string;
  readonly PROD?: boolean;
  // Add other environment variables here as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
