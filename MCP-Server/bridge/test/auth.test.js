// Unit tests for the bridge's sign-in code. Offline: no Microsoft service, no browser.
// Run: node --test MCP-Server/bridge/test/

import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import {
  authFetch,
  authSettings,
  createTokenProvider,
  defaultCachePath,
  filePlugin,
  openInBrowser,
} from "../server/auth.js";

const IDS = {
  INGENUS_TENANT_ID: "aaaaaaaa-0000-4000-8000-000000000001", // made-up ids
  INGENUS_CLIENT_ID: "cccccccc-0000-4000-8000-000000000003",
  INGENUS_SERVER_CLIENT_ID: "bbbbbbbb-0000-4000-8000-000000000002",
};

// ---- settings -------------------------------------------------------------------------------

test("no IDs means sign-in is off", () => {
  assert.equal(authSettings({}), null);
  assert.equal(authSettings({ INGENUS_TENANT_ID: "", INGENUS_CLIENT_ID: " " }), null);
});

test("all three IDs turn sign-in on and name the scope", () => {
  const s = authSettings(IDS);
  assert.equal(s.scope, `api://${IDS.INGENUS_SERVER_CLIENT_ID}/access_as_user`);
  assert.equal(s.tenantId, IDS.INGENUS_TENANT_ID);
});

test("a partial set is an error that names what is missing", () => {
  assert.throws(() => authSettings({ INGENUS_TENANT_ID: "t" }), /Desktop client ID, Server app ID/);
});

test("an unfilled placeholder counts as not set", () => {
  const env = {
    INGENUS_TENANT_ID: "${user_config.tenant_id}",
    INGENUS_CLIENT_ID: "${user_config.client_id}",
    INGENUS_SERVER_CLIENT_ID: "${user_config.server_client_id}",
  };
  assert.equal(authSettings(env), null);
});

// ---- the token goes on every request ---------------------------------------------------------

function fakeFetch(statuses) {
  const calls = [];
  const fn = async (input, init) => {
    calls.push({ input, authorization: new Headers(init.headers).get("authorization"), init });
    return new Response("body", { status: statuses.shift() ?? 200 });
  };
  fn.calls = calls;
  return fn;
}

test("authFetch adds the bearer token and keeps the other headers", async () => {
  const base = fakeFetch([200]);
  const f = authFetch(async () => "tok-1", base);
  const res = await f("https://s/mcp", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  assert.equal(res.status, 200);
  assert.equal(base.calls[0].authorization, "Bearer tok-1");
  assert.equal(new Headers(base.calls[0].init.headers).get("content-type"), "application/json");
  assert.equal(base.calls[0].init.body, "{}");
});

test("a 401 gets one retry with a freshly requested token", async () => {
  const base = fakeFetch([401, 200]);
  const asked = [];
  const f = authFetch(async ({ forceRefresh }) => {
    asked.push(forceRefresh);
    return forceRefresh ? "fresh" : "stale";
  }, base);
  const res = await f("https://s/mcp", { method: "POST", body: "{}" });
  assert.equal(res.status, 200);
  assert.deepEqual(asked, [false, true]);
  assert.deepEqual(base.calls.map((c) => c.authorization), ["Bearer stale", "Bearer fresh"]);
});

test("a second 401 is returned, not retried forever", async () => {
  const base = fakeFetch([401, 401, 200]);
  const f = authFetch(async () => "tok", base);
  const res = await f("https://s/mcp", { method: "POST", body: "{}" });
  assert.equal(res.status, 401);
  assert.equal(base.calls.length, 2);
});

test("other errors are passed through untouched", async () => {
  const base = fakeFetch([500]);
  const f = authFetch(async () => "tok", base);
  assert.equal((await f("https://s/mcp", {})).status, 500);
  assert.equal(base.calls.length, 1);
});

// ---- getting the token -----------------------------------------------------------------------

const SETTINGS = authSettings(IDS);

function fakeApp({ accounts = [], silent, interactive } = {}) {
  const app = {
    silentCalls: [],
    interactiveCalls: 0,
    async getAllAccounts() {
      return accounts;
    },
    async acquireTokenSilent(request) {
      app.silentCalls.push(request);
      if (silent instanceof Error) throw silent;
      return { accessToken: silent ?? "silent-token" };
    },
    async acquireTokenInteractive(request) {
      app.interactiveCalls += 1;
      app.lastInteractive = request;
      await new Promise((r) => setTimeout(r, 20));
      return { accessToken: interactive ?? "interactive-token", account: { username: "user@example.test" } };
    },
  };
  return app;
}

test("a cached account is renewed silently, with no browser", async () => {
  const app = fakeApp({ accounts: [{ username: "u" }] });
  const p = createTokenProvider({ settings: SETTINGS, app });
  assert.equal(await p.getToken(), "silent-token");
  assert.equal(app.interactiveCalls, 0);
  assert.deepEqual(app.silentCalls[0].scopes, [SETTINGS.scope]);
});

test("forceRefresh is passed on to the silent request", async () => {
  const app = fakeApp({ accounts: [{ username: "u" }] });
  await createTokenProvider({ settings: SETTINGS, app }).getToken({ forceRefresh: true });
  assert.equal(app.silentCalls[0].forceRefresh, true);
});

test("no account means the browser sign-in runs", async () => {
  const app = fakeApp();
  const p = createTokenProvider({ settings: SETTINGS, app });
  assert.equal(await p.getToken(), "interactive-token");
  assert.equal(app.interactiveCalls, 1);
  assert.deepEqual(app.lastInteractive.scopes, [SETTINGS.scope]);
  assert.equal(typeof app.lastInteractive.openBrowser, "function");
});

test("a failed silent renewal falls back to the browser", async () => {
  const app = fakeApp({ accounts: [{ username: "u" }], silent: Object.assign(new Error("x"), { errorCode: "interaction_required" }) });
  assert.equal(await createTokenProvider({ settings: SETTINGS, app }).getToken(), "interactive-token");
  assert.equal(app.interactiveCalls, 1);
});

test("a burst of requests shares one sign-in", async () => {
  const app = fakeApp();
  const p = createTokenProvider({ settings: SETTINGS, app });
  const tokens = await Promise.all([p.getToken(), p.getToken(), p.getToken()]);
  assert.deepEqual(tokens, ["interactive-token", "interactive-token", "interactive-token"]);
  assert.equal(app.interactiveCalls, 1);
});

test("the token is never written to the log", async () => {
  const lines = [];
  const app = fakeApp({ accounts: [{ username: "u" }], silent: "SECRET-TOKEN-VALUE" });
  await createTokenProvider({ settings: SETTINGS, app, log: (...a) => lines.push(a.join(" ")) }).getToken();
  assert.ok(!lines.join("\n").includes("SECRET-TOKEN-VALUE"));
});

// ---- the browser -----------------------------------------------------------------------------

test("only Microsoft's sign-in page is opened", async () => {
  await assert.rejects(openInBrowser("https://evil.example/login"), /not Microsoft's sign-in/);
  await assert.rejects(openInBrowser("file:///c:/windows/system32/calc.exe"), /not Microsoft's sign-in/);
});

test("the sign-in page is opened with a fixed program and the URL as one argument", async () => {
  let seen;
  const spawnFn = (cmd, args, opts) => {
    seen = { cmd, args, opts };
    return { on() {}, unref() {} };
  };
  const url = "https://login.microsoftonline.com/t/oauth2/v2.0/authorize?a=1&b=2";
  await openInBrowser(url, { spawnFn, platform: "win32" });
  assert.deepEqual(seen.args, ["url.dll,FileProtocolHandler", url]);
  assert.equal(seen.cmd, "rundll32");
  assert.notEqual(seen.opts.shell, true);
});

// ---- the cache file --------------------------------------------------------------------------

test("the token cache round-trips through a file and a first run is not an error", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "ingenus-bridge-"));
  const file = path.join(dir, "sub", "msal-cache.json");
  const plugin = filePlugin(file);
  let stored = "";
  const context = (changed) => ({
    cacheHasChanged: changed,
    tokenCache: { deserialize: (s) => (stored = s), serialize: () => '{"cache":"data"}' },
  });
  await plugin.beforeCacheAccess(context(false)); // no file yet: fine
  assert.equal(stored, "");
  await plugin.afterCacheAccess(context(false)); // nothing changed: nothing written
  await assert.rejects(fs.stat(file));
  await plugin.afterCacheAccess(context(true));
  assert.equal(await fs.readFile(file, "utf8"), '{"cache":"data"}');
  await plugin.beforeCacheAccess(context(false));
  assert.equal(stored, '{"cache":"data"}');
  await fs.rm(dir, { recursive: true });
});

test("the cache lives in the user's own profile folder", () => {
  assert.equal(
    defaultCachePath({ LOCALAPPDATA: "C:\\Users\\x\\AppData\\Local" }, "win32"),
    path.join("C:\\Users\\x\\AppData\\Local", "Ingenus", "bridge", "msal-cache.json"),
  );
});
