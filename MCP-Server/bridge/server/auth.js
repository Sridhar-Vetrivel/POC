// Sign-in for the Ingenus MCP bridge (V1-4, the laptop half).
//
// The bridge signs the user in to Microsoft Entra as a public client (the "Ingenus POC Desktop Client"
// app: no secret, loopback redirect to http://localhost) and gets an access token for the server's
// API scope. The token goes on every request to the server as "Authorization: Bearer ...". The first
// sign-in opens a browser; after that the cached refresh token renews the access token silently.
//
// The token is never logged. The cache file holds the refresh token, so it lives in the user's own
// profile folder and is written readable by that user only. It is NOT encrypted (a known limit of
// the POC; Windows DPAPI is the next step).
//
// Settings (all three needed to turn sign-in on; none is a secret):
//   INGENUS_TENANT_ID, INGENUS_CLIENT_ID (the desktop app), INGENUS_SERVER_CLIENT_ID (the server app)

import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

export const SCOPE_NAME = "access_as_user";
const SIGN_IN_TIMEOUT_MS = 5 * 60 * 1000;
const LOGIN_ORIGIN = "https://login.microsoftonline.com";

// A value the extension host did not fill in can arrive as an empty string or as the literal
// placeholder "${user_config.xyz}". Both mean "not set".
function clean(value) {
  const text = (value || "").trim();
  return text.startsWith("${") ? "" : text;
}

// null = sign-in off. An incomplete set is an error, not a silent fallback to "off".
export function authSettings(env) {
  const tenantId = clean(env.INGENUS_TENANT_ID);
  const clientId = clean(env.INGENUS_CLIENT_ID);
  const serverClientId = clean(env.INGENUS_SERVER_CLIENT_ID);
  if (!tenantId && !clientId && !serverClientId) return null;
  const missing = [
    ["Tenant ID", tenantId],
    ["Desktop client ID", clientId],
    ["Server app ID", serverClientId],
  ]
    .filter(([, v]) => !v)
    .map(([k]) => k);
  if (missing.length) {
    throw new Error(`Sign-in needs all three IDs in the extension settings; missing: ${missing.join(", ")}.`);
  }
  return { tenantId, clientId, serverClientId, scope: `api://${serverClientId}/${SCOPE_NAME}` };
}

export function defaultCachePath(env = process.env, platform = process.platform) {
  const base =
    platform === "win32"
      ? env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local")
      : path.join(os.homedir(), ".config");
  return path.join(base, "Ingenus", "bridge", "msal-cache.json");
}

// Persist MSAL's token cache in one file, readable by this user only.
export function filePlugin(cachePath) {
  return {
    async beforeCacheAccess(context) {
      try {
        context.tokenCache.deserialize(await fs.readFile(cachePath, "utf8"));
      } catch (err) {
        if (err?.code !== "ENOENT") throw err; // no file yet: first run
      }
    },
    async afterCacheAccess(context) {
      if (!context.cacheHasChanged) return;
      await fs.mkdir(path.dirname(cachePath), { recursive: true, mode: 0o700 });
      await fs.writeFile(cachePath, context.tokenCache.serialize(), { encoding: "utf8", mode: 0o600 });
    },
  };
}

// Open the sign-in page in the user's default browser. Only Microsoft's sign-in address is opened.
export async function openInBrowser(url, { spawnFn = spawn, platform = process.platform } = {}) {
  if (!url.startsWith(`${LOGIN_ORIGIN}/`)) {
    throw new Error("Refusing to open a page that is not Microsoft's sign-in.");
  }
  const [cmd, args] =
    platform === "win32"
      ? ["rundll32", ["url.dll,FileProtocolHandler", url]]
      : platform === "darwin"
        ? ["open", [url]]
        : ["xdg-open", [url]];
  const child = spawnFn(cmd, args, { stdio: "ignore", detached: true }); // fixed program, URL as one argument
  child.on?.("error", () => {});
  child.unref?.();
}

const SUCCESS_PAGE =
  "<html><body style='font-family:sans-serif'><h3>Signed in to Ingenus.</h3>You can close this tab and go back to Claude.</body></html>";
const ERROR_PAGE =
  "<html><body style='font-family:sans-serif'><h3>Sign-in did not finish.</h3>Go back to Claude and try again.</body></html>";

// Returns { getToken({ forceRefresh }) }. Concurrent calls share one sign-in, so a burst of requests
// opens one browser window, not several.
export function createTokenProvider({ settings, app, openBrowser = openInBrowser, log = () => {} }) {
  let inFlight = null;

  async function acquire(forceRefresh) {
    const accounts = await app.getAllAccounts();
    if (accounts.length) {
      try {
        const result = await app.acquireTokenSilent({ account: accounts[0], scopes: [settings.scope], forceRefresh });
        return result.accessToken;
      } catch (err) {
        log("silent sign-in not possible, asking the user:", err?.errorCode || err?.name || "error");
      }
    }
    log("opening the browser to sign in");
    const interactive = app.acquireTokenInteractive({
      scopes: [settings.scope],
      openBrowser,
      successTemplate: SUCCESS_PAGE,
      errorTemplate: ERROR_PAGE,
    });
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("Sign-in timed out after 5 minutes.")), SIGN_IN_TIMEOUT_MS);
    });
    try {
      const result = await Promise.race([interactive, timeout]);
      log("signed in as", result.account?.username || "(unknown)");
      return result.accessToken;
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    async getToken({ forceRefresh = false } = {}) {
      if (!inFlight) {
        inFlight = acquire(forceRefresh).finally(() => {
          inFlight = null;
        });
      }
      return inFlight;
    },
  };
}

export async function msalApp(settings, cachePath = defaultCachePath()) {
  // Imported here so a bridge with sign-in off, and the unit tests, never load the Microsoft library.
  const { PublicClientApplication } = await import("@azure/msal-node");
  return new PublicClientApplication({
    auth: { clientId: settings.clientId, authority: `https://login.microsoftonline.com/${settings.tenantId}` },
    cache: { cachePlugin: filePlugin(cachePath) },
  });
}

// A fetch that adds the user's token to every request, and, if the server answers 401 (token expired
// or revoked), gets a fresh token once and tries again. A second 401 is returned as it is.
export function authFetch(getToken, baseFetch = fetch, log = () => {}) {
  return async (input, init = {}) => {
    const send = async (forceRefresh) => {
      const token = await getToken({ forceRefresh });
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${token}`);
      return baseFetch(input, { ...init, headers });
    };
    const response = await send(false);
    if (response.status !== 401) return response;
    log("the server refused the token; getting a fresh one");
    await response.body?.cancel?.();
    return send(true);
  };
}
