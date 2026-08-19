import assert from "node:assert/strict";
import test from "node:test";

const originalDocument = globalThis.document;
const originalFetch = globalThis.fetch;
const originalNavigator = globalThis.navigator;
const originalWindow = globalThis.window;

function setBrowserGlobals({ fetch, locks }) {
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { cookie: "" },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: locks ? { locks } : {},
  });
  const storage = new Map([["travelplanner_refresh_token", "refresh-token"]]);
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { localStorage: { getItem: (key) => storage.get(key) ?? null, setItem() {}, removeItem() {} } },
  });
  globalThis.fetch = fetch;
}

function restoreBrowserGlobals() {
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: originalDocument,
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: originalNavigator,
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: originalWindow,
  });
  globalThis.fetch = originalFetch;
}

test("concurrent 401 responses share one refresh request", async () => {
  let authenticated = false;
  let refreshCount = 0;
  setBrowserGlobals({
    async fetch(url) {
      if (String(url).endsWith("/auth/refresh")) {
        refreshCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        authenticated = true;
        return new Response(JSON.stringify({ accessToken: "access-token", refreshToken: "refresh-token-2" }), { status: 200 });
      }
      return authenticated
        ? new Response(JSON.stringify({ ok: true }), { status: 200 })
        : new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED" }), {
            status: 401,
          });
    },
  });

  try {
    const { apiFetch } = await import(`./client.ts?single-flight=${Date.now()}`);
    const results = await Promise.all([
      apiFetch("/trip-chats"),
      apiFetch("/trip-chats/active-turns"),
      apiFetch("/url-import-jobs"),
    ]);
    assert.equal(refreshCount, 1);
    assert.deepEqual(results, [{ ok: true }, { ok: true }, { ok: true }]);
  } finally {
    restoreBrowserGlobals();
  }
});

test("browser lock serializes a token refresh", async () => {
  let refreshCount = 0;
  let protectedRequestCount = 0;
  setBrowserGlobals({
    locks: {
      async request(_name, callback) {
        return callback();
      },
    },
    async fetch(url) {
      if (String(url).endsWith("/auth/refresh")) {
        refreshCount += 1;
        return new Response(JSON.stringify({ accessToken: "access-token", refreshToken: "refresh-token-2" }), { status: 200 });
      }
      protectedRequestCount += 1;
      return protectedRequestCount === 1
        ? new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED" }), {
            status: 401,
          })
        : new Response(JSON.stringify({ ok: true }), { status: 200 });
    },
  });

  try {
    const { apiFetch } = await import(`./client.ts?cross-tab=${Date.now()}`);
    await apiFetch("/trip-chats");
    assert.equal(refreshCount, 1);
    assert.equal(protectedRequestCount, 2);
  } finally {
    restoreBrowserGlobals();
  }
});
