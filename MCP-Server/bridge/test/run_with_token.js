// Test helper, not shipped in the extension: runs the real bridge core with a fixed token taken from
// the environment instead of a Microsoft sign-in. Lets the Python tests drive Claude Desktop's side
// (stdio) against a server with sign-in on, fully offline.

import { runBridge, serverUrl } from "../server/bridge.js";

const url = serverUrl(process.env.INGENUS_MCP_URL);
const token = process.env.TEST_BEARER_TOKEN;
await runBridge({ url, getToken: token ? async () => token : undefined });
