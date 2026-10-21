// The forwarding core of the Ingenus MCP bridge.
//
// Claude Desktop talks MCP to the bridge over stdio. The bridge forwards every message, unchanged, to
// the central Ingenus MCP server over HTTP, and every reply and notification back. It holds no tools,
// no data and no secrets. When sign-in is on, `getToken` supplies the user's access token and the
// bridge adds it to every request (see auth.js); the bridge never reads or changes the messages.
//
// Never write to stdout except MCP messages: stdout is the protocol channel. Logs go to stderr,
// which Claude Desktop keeps in its MCP logs.

import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { authFetch } from "./auth.js";

export const log = (...args) => console.error("[ingenus-bridge]", ...args);

export function serverUrl(raw) {
  raw = (raw || "").trim();
  if (!raw) {
    throw new Error("INGENUS_MCP_URL is not set. Fill in the Server URL in the extension settings.");
  }
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`Server URL must be http or https, got ${url.protocol}`);
  }
  if (url.protocol === "http:" && !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
    // Plain HTTP is only acceptable on the same machine; anything on a network must be HTTPS.
    throw new Error("Use https:// for a server that is not on this machine.");
  }
  return url;
}

// A request Claude Desktop sent but the server could not receive gets a JSON-RPC error back, so
// Claude Desktop shows a failure instead of waiting forever.
export function errorReply(message, text) {
  if (message && typeof message === "object" && "id" in message && "method" in message) {
    return {
      jsonrpc: "2.0",
      id: message.id,
      error: { code: -32000, message: `Ingenus MCP server: ${text}` },
    };
  }
  return null;
}

// Runs until Claude Desktop closes the connection. `getToken` is optional: without it no sign-in
// header is added (the server must then have sign-in off, as on a loopback demo).
export async function runBridge({ url, getToken, desktop = new StdioServerTransport() }) {
  const options = getToken ? { fetch: authFetch(getToken, fetch, log) } : {};
  const server = new StreamableHTTPClientTransport(url, options);
  const pendingInitialize = new Set();
  let closing = false;

  desktop.onmessage = async (message) => {
    if (message?.method === "initialize" && "id" in message) pendingInitialize.add(message.id);
    try {
      await server.send(message);
    } catch (err) {
      log("send to server failed:", err?.message || err);
      const reply = errorReply(message, err?.message || String(err));
      if (reply) await desktop.send(reply);
    }
  };

  server.onmessage = async (message) => {
    // After the handshake the HTTP transport must send the agreed protocol version on every
    // request (the SDK's Client normally does this; a pure forwarder has to do it itself).
    if ("id" in message && pendingInitialize.has(message.id)) {
      pendingInitialize.delete(message.id);
      const version = message.result?.protocolVersion;
      if (version) server.setProtocolVersion(version);
    }
    await desktop.send(message);
  };

  const shutdown = async (why) => {
    if (closing) return;
    closing = true;
    log("closing:", why);
    try {
      await server.terminateSession();
    } catch {
      // the server may already be gone
    }
    await Promise.allSettled([server.close(), desktop.close()]);
    process.exit(0);
  };

  desktop.onclose = () => shutdown("Claude Desktop closed the connection");
  server.onclose = () => shutdown("server connection closed");
  desktop.onerror = (err) => log("stdio error:", err?.message || err);
  server.onerror = (err) => log("server error:", err?.message || err);

  await server.start();
  await desktop.start();
  log("forwarding to", url.origin + url.pathname, getToken ? "(signed in)" : "(no sign-in)");
}
