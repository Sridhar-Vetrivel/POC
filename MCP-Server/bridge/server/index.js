// Ingenus MCP bridge for Claude Desktop: entry point.
//
// Claude Desktop starts this file (with the Node it bundles). It reads the extension settings from the
// environment, sets up sign-in if the three IDs are given, and runs the forwarding core (bridge.js).
//
// Settings (from the extension's fields):
//   INGENUS_MCP_URL          the server address, e.g. http://127.0.0.1:8765/mcp
//   INGENUS_TENANT_ID, INGENUS_CLIENT_ID, INGENUS_SERVER_CLIENT_ID    all three, or none for no sign-in

import { authSettings, createTokenProvider, msalApp } from "./auth.js";
import { log, runBridge, serverUrl } from "./bridge.js";

async function main() {
  const url = serverUrl(process.env.INGENUS_MCP_URL);
  const settings = authSettings(process.env);
  let getToken;
  if (settings) {
    const provider = createTokenProvider({ settings, app: await msalApp(settings), log });
    getToken = provider.getToken;
  }
  await runBridge({ url, getToken });
}

main().catch((err) => {
  log("failed to start:", err?.message || err);
  process.exit(1);
});
