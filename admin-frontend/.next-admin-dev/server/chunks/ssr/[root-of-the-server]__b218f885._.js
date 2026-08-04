module.exports = [
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/action-async-storage.external.js [external] (next/dist/server/app-render/action-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/action-async-storage.external.js", () => require("next/dist/server/app-render/action-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[project]/lib/api.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "APIError",
    ()=>APIError,
    "applyGraphImport",
    ()=>applyGraphImport,
    "createGraphImport",
    ()=>createGraphImport,
    "deleteGraphImport",
    ()=>deleteGraphImport,
    "deleteProposedGraphEdge",
    ()=>deleteProposedGraphEdge,
    "deleteProposedGraphNode",
    ()=>deleteProposedGraphNode,
    "getGraphImport",
    ()=>getGraphImport,
    "getGraphImportMeta",
    ()=>getGraphImportMeta,
    "getRun",
    ()=>getRun,
    "listGoldenCases",
    ()=>listGoldenCases,
    "listGraphImportEdges",
    ()=>listGraphImportEdges,
    "listGraphImportNodes",
    ()=>listGraphImportNodes,
    "listGraphImports",
    ()=>listGraphImports,
    "listRuns",
    ()=>listRuns,
    "loadKnowledgeGraphFiles",
    ()=>loadKnowledgeGraphFiles,
    "login",
    ()=>login,
    "logout",
    ()=>logout,
    "revalidateGraphImport",
    ()=>revalidateGraphImport,
    "runGoldenCase",
    ()=>runGoldenCase,
    "saveKnowledgeGraphFile",
    ()=>saveKnowledgeGraphFile,
    "saveKnowledgeGraphFiles",
    ()=>saveKnowledgeGraphFiles,
    "testConstraintResearch",
    ()=>testConstraintResearch,
    "testFestivalDiscovery",
    ()=>testFestivalDiscovery,
    "testRegionOverview",
    ()=>testRegionOverview,
    "updateGoldenCaseInput",
    ()=>updateGoldenCaseInput,
    "updateProposedGraphEdge",
    ()=>updateProposedGraphEdge,
    "updateProposedGraphNode",
    ()=>updateProposedGraphNode
]);
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
class APIError extends Error {
    status;
    code;
    constructor(status, code, message){
        super(message), this.status = status, this.code = code;
    }
}
function cookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    return document.cookie.split("; ").find((item)=>item.startsWith(prefix))?.slice(prefix.length);
}
async function parseError(response) {
    let body = {};
    try {
        body = await response.json();
    } catch  {
    // Use the stable fallback below.
    }
    return new APIError(response.status, body.code ?? "REQUEST_FAILED", body.message ?? body.detail ?? "Không thể hoàn thành yêu cầu.");
}
async function refreshSession() {
    const csrf = cookie("vsf_csrf");
    if (!csrf) return false;
    const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: {
            "X-CSRF-Token": decodeURIComponent(csrf)
        }
    });
    return response.ok;
}
async function request(path, init = {}, retry = true) {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    if (![
        "GET",
        "HEAD"
    ].includes((init.method ?? "GET").toUpperCase())) {
        const csrf = cookie("vsf_csrf");
        if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
    }
    let response;
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...init,
            headers,
            credentials: "include"
        });
    } catch  {
        throw new APIError(0, "NETWORK_ERROR", "Không kết nối được backend VSF Travel.");
    }
    if (response.status === 401 && retry && !path.startsWith("/auth/") && await refreshSession()) {
        return request(path, init, false);
    }
    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return undefined;
    return response.json();
}
async function login(email, password) {
    const response = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({
            email,
            password
        })
    });
    if (response.user.role !== "admin") {
        await logout();
        throw new APIError(403, "ADMIN_REQUIRED", "Tài khoản này không có quyền quản trị.");
    }
    return response.user;
}
async function logout() {
    await request("/auth/logout", {
        method: "POST"
    });
}
function listRuns(filters) {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.stage) params.set("stage", filters.stage);
    if (filters.query) params.set("query", filters.query);
    params.set("limit", String(filters.limit ?? 100));
    return request(`/admin/planning-runs?${params.toString()}`);
}
function getRun(runId) {
    return request(`/admin/planning-runs/${runId}`);
}
function listGoldenCases(module = "") {
    const params = new URLSearchParams();
    if (module) params.set("module", module);
    return request(`/admin/planning-runs/golden/cases?${params.toString()}`);
}
function runGoldenCase(caseId) {
    return request(`/admin/planning-runs/golden/cases/${encodeURIComponent(caseId)}/run`, {
        method: "POST"
    });
}
function updateGoldenCaseInput(caseId, input) {
    return request(`/admin/planning-runs/golden/cases/${encodeURIComponent(caseId)}`, {
        method: "PUT",
        body: JSON.stringify(input)
    });
}
function testRegionOverview(input) {
    return request(`/admin/planning-runs/tools/region-overview`, {
        method: "POST",
        body: JSON.stringify(input)
    });
}
function testConstraintResearch(input) {
    return request(`/admin/planning-runs/tools/constraint-research`, {
        method: "POST",
        body: JSON.stringify(input)
    });
}
function testFestivalDiscovery(input) {
    return request(`/admin/planning-runs/tools/festival-discovery`, {
        method: "POST",
        body: JSON.stringify(input)
    });
}
async function loadKnowledgeGraphFiles() {
    const response = await fetch("/api/knowledge-graph", {
        cache: "no-store",
        credentials: "include"
    });
    if (!response.ok) throw await parseError(response);
    const payload = await response.json();
    return payload.files;
}
async function saveKnowledgeGraphFile(fileName, content) {
    const csrf = cookie("vsf_csrf");
    const response = await fetch("/api/knowledge-graph", {
        method: "PUT",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...csrf ? {
                "X-CSRF-Token": decodeURIComponent(csrf)
            } : {}
        },
        body: JSON.stringify({
            fileName,
            content
        })
    });
    if (!response.ok) throw await parseError(response);
}
async function saveKnowledgeGraphFiles(files) {
    const csrf = cookie("vsf_csrf");
    const response = await fetch("/api/knowledge-graph", {
        method: "PUT",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...csrf ? {
                "X-CSRF-Token": decodeURIComponent(csrf)
            } : {}
        },
        body: JSON.stringify({
            files
        })
    });
    if (!response.ok) throw await parseError(response);
}
function listGraphImports(filters = {}) {
    const params = new URLSearchParams();
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
    if (filters.status) params.set("status", filters.status);
    if (filters.search) params.set("search", filters.search);
    const query = params.toString();
    return request(`/admin/knowledge-graph/imports${query ? `?${query}` : ""}`);
}
function getGraphImportMeta(importId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/meta`);
}
function getGraphImport(importId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}`);
}
function listGraphImportNodes(importId, filters = {}) {
    const params = new URLSearchParams();
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
    const query = params.toString();
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes${query ? `?${query}` : ""}`);
}
function listGraphImportEdges(importId, filters = {}) {
    const params = new URLSearchParams();
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
    const query = params.toString();
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges${query ? `?${query}` : ""}`);
}
function createGraphImport(payload) {
    return request("/admin/knowledge-graph/imports", {
        method: "POST",
        body: JSON.stringify(payload)
    });
}
function updateProposedGraphNode(importId, tempId, payload) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes/${encodeURIComponent(tempId)}`, {
        method: "PUT",
        body: JSON.stringify(payload)
    });
}
function updateProposedGraphEdge(importId, tempId, payload) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges/${encodeURIComponent(tempId)}`, {
        method: "PUT",
        body: JSON.stringify(payload)
    });
}
function applyGraphImport(importId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/apply`, {
        method: "POST"
    });
}
function revalidateGraphImport(importId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/revalidate`, {
        method: "POST"
    });
}
function deleteProposedGraphNode(importId, tempId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes/${encodeURIComponent(tempId)}`, {
        method: "DELETE"
    });
}
function deleteProposedGraphEdge(importId, tempId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges/${encodeURIComponent(tempId)}`, {
        method: "DELETE"
    });
}
function deleteGraphImport(importId) {
    return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}`, {
        method: "DELETE"
    });
}
}),
"[project]/app/(dashboard)/layout.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>DashboardLayout
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/client/app-dir/link.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/navigation.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
;
;
function DashboardLayout({ children }) {
    const [authenticated, setAuthenticated] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [user, setUser] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const router = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRouter"])();
    const pathname = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["usePathname"])();
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        // A quick way to verify if we are logged in
        (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["listRuns"])({
            limit: 1
        }).then(()=>{
            // Assume logged in if it succeeds
            // We don't get the user info from listRuns directly in the old code either
            setAuthenticated(true);
        }).catch(()=>{
            setAuthenticated(false);
            router.push("/login");
        });
    }, [
        router
    ]);
    if (authenticated === null) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
            className: "bootScreen",
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "bootMark",
                    children: "VSF"
                }, void 0, false, {
                    fileName: "[project]/app/(dashboard)/layout.tsx",
                    lineNumber: 35,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                    children: "Đang xác thực Planning Control…"
                }, void 0, false, {
                    fileName: "[project]/app/(dashboard)/layout.tsx",
                    lineNumber: 36,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/app/(dashboard)/layout.tsx",
            lineNumber: 34,
            columnNumber: 7
        }, this);
    }
    if (!authenticated) {
        return null; // Will redirect
    }
    async function signOut() {
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["logout"])();
        } finally{
            router.push("/login");
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
        className: "appShell",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                className: "sidebar",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "sidebarBrand",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "VSF"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 57,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Planning"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 59,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: "Control room"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 60,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 58,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/layout.tsx",
                        lineNumber: 56,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("nav", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                                href: "/runs",
                                className: pathname === "/runs" ? "active" : "",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "⌁"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 65,
                                        columnNumber: 13
                                    }, this),
                                    " Planning runs"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 64,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                                href: "/golden",
                                className: pathname === "/golden" ? "active" : "",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "◇"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 68,
                                        columnNumber: 13
                                    }, this),
                                    " Golden dataset"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 67,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                                href: "/knowledge-graph",
                                className: pathname === "/knowledge-graph" ? "active" : "",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "⌘"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 74,
                                        columnNumber: 13
                                    }, this),
                                    " Knowledge Graph"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 70,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                                href: "/tools",
                                className: pathname === "/tools" ? "active" : "",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "⌂"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 77,
                                        columnNumber: 13
                                    }, this),
                                    " Tools Tester"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 76,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/layout.tsx",
                        lineNumber: 63,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "sidebarFoot",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "adminAvatar",
                                children: user?.fullName?.slice(0, 1) ?? "A"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 81,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: user?.fullName ?? "VSF Admin"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 83,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: user?.email ?? "Authenticated session"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/layout.tsx",
                                        lineNumber: 84,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 82,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                type: "button",
                                onClick: signOut,
                                "aria-label": "Đăng xuất",
                                children: "↗"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/layout.tsx",
                                lineNumber: 86,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/layout.tsx",
                        lineNumber: 80,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/layout.tsx",
                lineNumber: 55,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                className: "workspace",
                children: children
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/layout.tsx",
                lineNumber: 91,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/layout.tsx",
        lineNumber: 54,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__b218f885._.js.map