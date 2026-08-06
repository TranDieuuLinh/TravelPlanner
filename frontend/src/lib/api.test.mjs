import assert from "node:assert/strict";
import test from "node:test";

const originalDocument = globalThis.document;
const originalFetch = globalThis.fetch;
const originalNavigator = globalThis.navigator;

function setBrowserGlobals({ fetch, locks }) {
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { cookie: "vsf_csrf=csrf-token" },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: locks ? { locks } : {},
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
        return new Response(JSON.stringify({ user: {} }), { status: 200 });
      }
      return authenticated
        ? new Response(JSON.stringify({ ok: true }), { status: 200 })
        : new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED" }), {
            status: 401,
          });
    },
  });

  try {
    const { apiFetch } = await import(`./api.ts?single-flight=${Date.now()}`);
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

test("a waiting tab reuses cookies rotated by the lock holder", async () => {
  let refreshCount = 0;
  let protectedRequestCount = 0;
  setBrowserGlobals({
    locks: {
      async request(_name, callback) {
        globalThis.document.cookie = "vsf_csrf=rotated-token";
        return callback();
      },
    },
    async fetch(url) {
      if (String(url).endsWith("/auth/refresh")) {
        refreshCount += 1;
        return new Response(JSON.stringify({ user: {} }), { status: 200 });
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
    const { apiFetch } = await import(`./api.ts?cross-tab=${Date.now()}`);
    await apiFetch("/trip-chats");
    assert.equal(refreshCount, 0);
    assert.equal(protectedRequestCount, 2);
  } finally {
    restoreBrowserGlobals();
  }
});
