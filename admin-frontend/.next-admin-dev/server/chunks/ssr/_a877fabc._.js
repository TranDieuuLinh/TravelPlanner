module.exports = [
"[project]/lib/knowledge-graph.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "aliases",
    ()=>aliases,
    "initialEntities",
    ()=>initialEntities,
    "ontologyNodes",
    ()=>ontologyNodes,
    "ontologyRelationships",
    ()=>ontologyRelationships,
    "parseAliases",
    ()=>parseAliases,
    "parseEntities",
    ()=>parseEntities,
    "parseOntology",
    ()=>parseOntology,
    "parseRelationships",
    ()=>parseRelationships,
    "rawDataset",
    ()=>rawDataset,
    "serializeAliases",
    ()=>serializeAliases,
    "serializeEntities",
    ()=>serializeEntities,
    "serializeOntology",
    ()=>serializeOntology,
    "serializeRelationships",
    ()=>serializeRelationships,
    "serializeSchema",
    ()=>serializeSchema,
    "validateKnowledgeGraph",
    ()=>validateKnowledgeGraph
]);
const initialEntities = [
    {
        id: "place_001",
        name: "Hồ Hoàn Kiếm",
        type: "Place",
        status: "missing",
        aliases: [
            "Hồ Hoàn Kiếm",
            "Hoan Kiem Lake"
        ],
        properties: {},
        sourceFile: "aliases.csv"
    },
    {
        id: "restaurant_001",
        name: "Bún Chả Obama",
        type: "Restaurant",
        status: "missing",
        aliases: [
            "Bún Chả Obama"
        ],
        properties: {},
        sourceFile: "aliases.csv"
    }
];
const aliases = [
    {
        entityId: "place_001",
        alias: "Hồ Hoàn Kiếm",
        language: "vi"
    },
    {
        entityId: "place_001",
        alias: "Hoan Kiem Lake",
        language: "en"
    },
    {
        entityId: "restaurant_001",
        alias: "Bún Chả Obama",
        language: "vi"
    }
];
const ontologyNodes = [
    {
        type: "Place",
        description: "Điểm tham quan"
    },
    {
        type: "City",
        description: null
    },
    {
        type: "Restaurant",
        description: "Nhà hàng"
    },
    {
        type: "Food",
        description: null
    }
];
const ontologyRelationships = [
    {
        type: "LOCATED_IN",
        from: "Place",
        to: "City",
        description: "Địa điểm thuộc một thành phố"
    },
    {
        type: "SERVES",
        from: "Restaurant",
        to: "Food",
        description: "Nhà hàng phục vụ món ăn"
    },
    {
        type: "NEAR",
        from: null,
        to: null,
        description: "Có trong schema nhưng chưa được khai báo trong ontology"
    }
];
const rawDataset = {
    "aliases.csv": "entity_id,alias\nplace_001,Hồ Hoàn Kiếm\nplace_001,Hoan Kiem Lake\nrestaurant_001,Bún Chả Obama",
    "entities.csv": "id,name,type,status\n",
    "ontology.yaml": "Place:\n  description: Điểm tham quan\n\nRestaurant:\n  description: Nhà hàng\n\nLOCATED_IN:\n  from: Place\n  to: City\n\nSERVES:\n  from: Restaurant\n  to: Food",
    "properties.csv": "",
    "relationships.csv": "from_entity_id,relationship,to_entity_id,source\n",
    "schema.yaml": "nodes:\n  - Place\n  - City\n  - Restaurant\n  - Food\n\nrelationships:\n  - LOCATED_IN\n  - SERVES\n  - NEAR\n\nconstraints:\n  Place.id: unique\n  Restaurant.id: unique"
};
function parseCsvRows(content) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    for(let index = 0; index < content.length; index += 1){
        const character = content[index];
        const next = content[index + 1];
        if (character === '"' && quoted && next === '"') {
            field += '"';
            index += 1;
        } else if (character === '"') {
            quoted = !quoted;
        } else if (character === "," && !quoted) {
            row.push(field);
            field = "";
        } else if ((character === "\n" || character === "\r") && !quoted) {
            if (character === "\r" && next === "\n") index += 1;
            row.push(field);
            if (row.some((value)=>value.length > 0)) rows.push(row);
            row = [];
            field = "";
        } else {
            field += character;
        }
    }
    if (field.length > 0 || row.length > 0) {
        row.push(field);
        if (row.some((value)=>value.length > 0)) rows.push(row);
    }
    return rows;
}
function csvCell(value) {
    return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}
function parseAliases(content) {
    return parseCsvRows(content).slice(1).filter((row)=>row[0]?.trim() && row[1]?.trim()).map((row)=>({
            entityId: row[0].trim(),
            alias: row[1].trim(),
            language: /[À-ỹ]/u.test(row[1]) ? "vi" : "en"
        }));
}
function serializeAliases(items) {
    return [
        "entity_id,alias",
        ...items.map((item)=>[
                item.entityId,
                item.alias
            ].map(csvCell).join(","))
    ].join("\r\n");
}
function parseEntities(content) {
    return parseCsvRows(content).slice(1).filter((row)=>row[0]?.trim() && row[1]?.trim() && row[2]?.trim()).map((row)=>({
            id: row[0].trim(),
            name: row[1].trim(),
            type: row[2].trim(),
            status: row[3]?.trim() === "verified" ? "verified" : "draft",
            aliases: [],
            properties: {},
            sourceFile: "entities.csv"
        }));
}
function serializeEntities(items) {
    return [
        "id,name,type,status",
        ...items.filter((item)=>item.status !== "missing").map((item)=>[
                item.id,
                item.name,
                item.type,
                item.status
            ].map(csvCell).join(","))
    ].join("\r\n");
}
function parseRelationships(content) {
    return parseCsvRows(content).slice(1).filter((row)=>row[0]?.trim() && row[1]?.trim() && row[2]?.trim()).map((row, index)=>({
            id: `relationship-${index}-${row[0]}-${row[2]}`,
            fromEntityId: row[0].trim(),
            relationship: row[1].trim(),
            toEntityId: row[2].trim(),
            source: row[3]?.trim() ?? ""
        }));
}
function serializeRelationships(items) {
    return [
        "from_entity_id,relationship,to_entity_id,source",
        ...items.map((item)=>[
                item.fromEntityId,
                item.relationship,
                item.toEntityId,
                item.source
            ].map(csvCell).join(","))
    ].join("\r\n");
}
function parseOntology(content) {
    const blocks = content.split(/\r?\n(?=\S)/).map((block)=>block.trim()).filter(Boolean);
    const nodes = [];
    const relationships = [];
    blocks.forEach((block)=>{
        const lines = block.split(/\r?\n/);
        const name = lines[0]?.replace(/:$/, "").trim();
        if (!name) return;
        const fields = Object.fromEntries(lines.slice(1).map((line)=>{
            const separator = line.indexOf(":");
            return [
                line.slice(0, separator).trim(),
                separator >= 0 ? line.slice(separator + 1).trim() : ""
            ];
        }));
        if ("from" in fields || "to" in fields) {
            relationships.push({
                type: name,
                from: fields.from || null,
                to: fields.to || null,
                description: fields.description || "Relationship ontology contract"
            });
        } else {
            nodes.push({
                type: name,
                description: fields.description || null
            });
        }
    });
    return {
        nodes,
        relationships
    };
}
function serializeOntology(nodes, relationships) {
    const nodeBlocks = nodes.map((node)=>`${node.type}:\n  description: ${node.description ?? ""}`);
    const relationshipBlocks = relationships.map((relationship)=>[
            `${relationship.type}:`,
            `  from: ${relationship.from ?? ""}`,
            `  to: ${relationship.to ?? ""}`,
            relationship.description && relationship.description !== "Relationship ontology contract" ? `  description: ${relationship.description}` : null
        ].filter(Boolean).join("\n"));
    return [
        ...nodeBlocks,
        ...relationshipBlocks
    ].join("\n\n");
}
function serializeSchema(nodes, relationships, currentSchema) {
    const constraintIndex = currentSchema.search(/^constraints:/m);
    const constraints = constraintIndex >= 0 ? currentSchema.slice(constraintIndex).trim() : "constraints: {}";
    return [
        "nodes:",
        ...nodes.map((node)=>`  - ${node.type}`),
        "",
        "relationships:",
        ...relationships.map((relationship)=>`  - ${relationship.type}`),
        "",
        constraints
    ].join("\n");
}
function validateKnowledgeGraph(entities, relationships = [], nodes = ontologyNodes, relationshipDefinitions = ontologyRelationships) {
    const issues = [];
    const persistedEntities = entities.filter((entity)=>entity.status !== "missing");
    if (persistedEntities.length === 0) {
        issues.push({
            id: "entities-empty",
            severity: "error",
            title: "Chưa có entity chính thức",
            message: "entities.csv đang rỗng; aliases hiện không có bản ghi đích hợp lệ.",
            path: "entities.csv",
            target: "entities"
        });
    }
    entities.filter((entity)=>entity.status === "missing").forEach((entity)=>{
        issues.push({
            id: `missing-${entity.id}`,
            severity: "error",
            title: `Không tìm thấy ${entity.id}`,
            message: `${entity.aliases.length} alias đang tham chiếu entity chưa tồn tại.`,
            path: `aliases.csv → ${entity.id}`,
            entityId: entity.id,
            target: "entities"
        });
    });
    if (relationships.length === 0) {
        issues.push({
            id: "relationships-empty",
            severity: "warning",
            title: "Chưa có relationship",
            message: "relationships.csv đang rỗng nên graph chưa có cạnh dữ liệu.",
            path: "relationships.csv",
            target: "relationships"
        });
    }
    relationships.filter((relationship)=>!relationship.source.trim()).forEach((relationship)=>{
        issues.push({
            id: `relationship-source-${relationship.id}`,
            severity: "error",
            title: "Relationship thiếu nguồn",
            message: `${relationship.fromEntityId} → ${relationship.toEntityId} chưa có provenance.`,
            path: `relationships.csv.${relationship.id}.source`,
            target: "relationships"
        });
    });
    issues.push({
        id: "properties-empty",
        severity: "warning",
        title: "Chưa có properties",
        message: "properties.csv đang rỗng; entity chưa có thuộc tính nghiệp vụ.",
        path: "properties.csv",
        target: "entities"
    });
    const nearDefinition = relationshipDefinitions.find((item)=>item.type === "NEAR");
    if (!nearDefinition?.from || !nearDefinition.to) {
        issues.push({
            id: "near-incomplete",
            severity: "error",
            title: "NEAR chưa có contract",
            message: "NEAR xuất hiện trong schema nhưng chưa xác định node nguồn và node đích.",
            path: "schema.yaml.relationships.NEAR",
            target: "ontology"
        });
    }
    nodes.filter((node)=>!node.description).forEach((node)=>{
        issues.push({
            id: `description-${node.type}`,
            severity: "warning",
            title: `${node.type} chưa có mô tả`,
            message: "Node đã có trong schema nhưng chưa được mô tả trong ontology.",
            path: `ontology.yaml.${node.type}`,
            target: "ontology"
        });
    });
    return issues;
}
}),
"[project]/app/(dashboard)/knowledge-graph/page.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>KnowledgeGraphPage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/knowledge-graph.ts [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
;
const TABS = [
    {
        id: "entities",
        label: "Entities"
    },
    {
        id: "aliases",
        label: "Aliases"
    },
    {
        id: "relationships",
        label: "Relationships"
    },
    {
        id: "ontology",
        label: "Ontology"
    },
    {
        id: "validation",
        label: "Validation"
    }
];
const TYPES = [
    "all",
    "Place",
    "City",
    "Restaurant",
    "Food"
];
const STATUS_LABELS = {
    missing: "Thiếu entity",
    draft: "Bản nháp",
    verified: "Đã xác minh"
};
function severityLabel(severity) {
    return severity === "error" ? "Lỗi" : severity === "warning" ? "Cảnh báo" : "Thông tin";
}
function KnowledgeGraphPage() {
    const [entities, setEntities] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["initialEntities"]);
    const [aliasRows, setAliasRows] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])((0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseAliases"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["rawDataset"]["aliases.csv"]));
    const [relationshipRows, setRelationshipRows] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [nodeDefinitions, setNodeDefinitions] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ontologyNodes"]);
    const [relationshipDefinitions, setRelationshipDefinitions] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ontologyRelationships"]);
    const [datasetFiles, setDatasetFiles] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["rawDataset"]);
    const [datasetLoading, setDatasetLoading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(true);
    const [saving, setSaving] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [activeTab, setActiveTab] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("entities");
    const [selectedId, setSelectedId] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["initialEntities"][0]?.id ?? "");
    const [query, setQuery] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [typeFilter, setTypeFilter] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("all");
    const [statusFilter, setStatusFilter] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("all");
    const [notice, setNotice] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [validatedAt, setValidatedAt] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [importedFiles, setImportedFiles] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [entityEditor, setEntityEditor] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [entityDraft, setEntityDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({
        id: "",
        name: "",
        type: "Place",
        status: "draft"
    });
    const importInputRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const issues = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>(0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["validateKnowledgeGraph"])(entities, relationshipRows, nodeDefinitions, relationshipDefinitions), [
        entities,
        nodeDefinitions,
        relationshipDefinitions,
        relationshipRows
    ]);
    const errorCount = issues.filter((issue)=>issue.severity === "error").length;
    const persistedCount = entities.filter((entity)=>entity.status !== "missing").length;
    const selectedEntity = entities.find((entity)=>entity.id === selectedId) ?? null;
    const filteredEntities = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        const normalizedQuery = query.trim().toLocaleLowerCase("vi");
        return entities.filter((entity)=>{
            const matchesQuery = !normalizedQuery || entity.id.toLocaleLowerCase("vi").includes(normalizedQuery) || entity.name.toLocaleLowerCase("vi").includes(normalizedQuery) || entity.aliases.some((alias)=>alias.toLocaleLowerCase("vi").includes(normalizedQuery));
            const matchesType = typeFilter === "all" || entity.type === typeFilter;
            const matchesStatus = statusFilter === "all" || entity.status === statusFilter;
            return matchesQuery && matchesType && matchesStatus;
        });
    }, [
        entities,
        query,
        statusFilter,
        typeFilter
    ]);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        let active = true;
        (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["loadKnowledgeGraphFiles"])().then((files)=>{
            if (!active) return;
            const loadedAliases = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseAliases"])(files["aliases.csv"]);
            const loadedEntities = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseEntities"])(files["entities.csv"]);
            const loadedRelationships = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseRelationships"])(files["relationships.csv"]);
            const loadedOntology = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseOntology"])(files["ontology.yaml"]);
            const mergedNodes = [
                ...loadedOntology.nodes,
                ...__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ontologyNodes"].filter((fallback)=>!loadedOntology.nodes.some((item)=>item.type === fallback.type))
            ];
            const mergedRelationships = [
                ...loadedOntology.relationships,
                ...__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ontologyRelationships"].filter((fallback)=>!loadedOntology.relationships.some((item)=>item.type === fallback.type))
            ];
            const referenced = Array.from(new Set([
                ...loadedAliases.map((item)=>item.entityId),
                ...loadedRelationships.flatMap((item)=>[
                        item.fromEntityId,
                        item.toEntityId
                    ])
            ]));
            setAliasRows(loadedAliases);
            setRelationshipRows(loadedRelationships);
            setNodeDefinitions(mergedNodes);
            setRelationshipDefinitions(mergedRelationships);
            setDatasetFiles(files);
            const combinedEntities = loadedEntities.map((entity)=>({
                    ...entity,
                    aliases: loadedAliases.filter((item)=>item.entityId === entity.id).map((item)=>item.alias)
                }));
            referenced.forEach((entityId)=>{
                if (combinedEntities.some((item)=>item.id === entityId)) return;
                const entityAliases = loadedAliases.filter((item)=>item.entityId === entityId);
                const current = __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["initialEntities"].find((item)=>item.id === entityId);
                const relatedEdge = loadedRelationships.find((item)=>item.fromEntityId === entityId || item.toEntityId === entityId);
                const relatedDefinition = mergedRelationships.find((item)=>item.type === relatedEdge?.relationship);
                const inferredType = relatedEdge?.fromEntityId === entityId ? relatedDefinition?.from : relatedDefinition?.to;
                combinedEntities.push(current ? {
                    ...current,
                    aliases: entityAliases.map((item)=>item.alias)
                } : {
                    id: entityId,
                    name: entityAliases[0]?.alias ?? entityId,
                    type: inferredType ?? "Place",
                    status: "missing",
                    aliases: entityAliases.map((item)=>item.alias),
                    properties: {},
                    sourceFile: "aliases.csv"
                });
            });
            setEntities(combinedEntities);
        }).catch((error)=>{
            if (active) setNotice(error instanceof Error ? error.message : "Không đọc được knowledge graph.");
        }).finally(()=>{
            if (active) setDatasetLoading(false);
        });
        return ()=>{
            active = false;
        };
    }, []);
    async function persistFile(fileName, content, successMessage) {
        setSaving(true);
        setNotice("");
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["saveKnowledgeGraphFile"])(fileName, content);
            setDatasetFiles((current)=>({
                    ...current,
                    [fileName]: content
                }));
            setNotice(successMessage);
        } catch (error) {
            setNotice(error instanceof Error ? error.message : `Không lưu được ${fileName}.`);
            throw error;
        } finally{
            setSaving(false);
        }
    }
    async function persistFiles(updates, successMessage) {
        setSaving(true);
        setNotice("");
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["saveKnowledgeGraphFiles"])(updates);
            setDatasetFiles((current)=>({
                    ...current,
                    ...updates
                }));
            setNotice(successMessage);
        } catch (error) {
            setNotice(error instanceof Error ? error.message : "Không lưu được knowledge graph.");
            throw error;
        } finally{
            setSaving(false);
        }
    }
    async function saveAliases(nextRows) {
        const content = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeAliases"])(nextRows);
        await persistFile("aliases.csv", content, "Đã lưu thay đổi trực tiếp vào aliases.csv.");
        setAliasRows(nextRows);
        setEntities((current)=>{
            const referencedIds = new Set([
                ...nextRows.map((item)=>item.entityId),
                ...relationshipRows.flatMap((item)=>[
                        item.fromEntityId,
                        item.toEntityId
                    ])
            ]);
            const nextEntities = current.filter((entity)=>entity.status !== "missing" || referencedIds.has(entity.id)).map((entity)=>({
                    ...entity,
                    aliases: nextRows.filter((item)=>item.entityId === entity.id).map((item)=>item.alias)
                }));
            referencedIds.forEach((entityId)=>{
                if (nextEntities.some((entity)=>entity.id === entityId)) return;
                const entityAliases = nextRows.filter((item)=>item.entityId === entityId).map((item)=>item.alias);
                nextEntities.push({
                    id: entityId,
                    name: entityAliases[0] ?? entityId,
                    type: "Place",
                    status: "missing",
                    aliases: entityAliases,
                    properties: {},
                    sourceFile: "aliases.csv"
                });
            });
            return nextEntities;
        });
    }
    function beginAddEntity(prefill) {
        setEntityEditor(prefill?.id ?? "new");
        setEntityDraft({
            id: prefill?.id ?? "",
            name: prefill?.name ?? "",
            type: prefill?.type ?? "Place",
            status: prefill?.status === "verified" ? "verified" : "draft"
        });
    }
    function beginEditEntity(entity) {
        setEntityEditor(entity.id);
        setEntityDraft({
            id: entity.id,
            name: entity.name,
            type: entity.type,
            status: entity.status
        });
    }
    async function submitEntity(event) {
        event.preventDefault();
        if (!entityDraft.id.trim() || !entityDraft.name.trim() || !entityDraft.type.trim()) {
            setNotice("ID, tên và loại entity là bắt buộc.");
            return;
        }
        const duplicate = entities.some((item)=>item.id === entityDraft.id.trim() && item.id !== entityEditor);
        if (duplicate) {
            setNotice(`Entity ID ${entityDraft.id.trim()} đã tồn tại.`);
            return;
        }
        const nextEntity = {
            id: entityDraft.id.trim(),
            name: entityDraft.name.trim(),
            type: entityDraft.type.trim(),
            status: entityDraft.status,
            aliases: aliasRows.filter((item)=>item.entityId === entityDraft.id.trim()).map((item)=>item.alias),
            properties: {},
            sourceFile: "entities.csv"
        };
        const isExisting = entityEditor !== "new" && entities.some((item)=>item.id === entityEditor);
        const nextEntities = isExisting ? entities.map((item)=>item.id === entityEditor ? nextEntity : item) : [
            ...entities.filter((item)=>item.id !== nextEntity.id),
            nextEntity
        ];
        try {
            await persistFile("entities.csv", (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeEntities"])(nextEntities), "Đã lưu entity trực tiếp vào entities.csv.");
            setEntities(nextEntities);
            setSelectedId(nextEntity.id);
            setEntityEditor(null);
        } catch  {
        // persistFile displays the error.
        }
    }
    async function deleteEntity(entity) {
        if (entity.status === "missing") return;
        if (!window.confirm(`Xóa entity ${entity.id} khỏi entities.csv? Alias và relationship tham chiếu sẽ được giữ lại để validation báo lỗi.`)) return;
        const hasReferences = aliasRows.some((item)=>item.entityId === entity.id) || relationshipRows.some((item)=>item.fromEntityId === entity.id || item.toEntityId === entity.id);
        const nextEntities = hasReferences ? entities.map((item)=>item.id === entity.id ? {
                ...item,
                status: "missing",
                sourceFile: "aliases.csv"
            } : item) : entities.filter((item)=>item.id !== entity.id);
        try {
            await persistFile("entities.csv", (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeEntities"])(nextEntities), `Đã xóa ${entity.id} khỏi entities.csv.`);
            setEntities(nextEntities);
            setSelectedId(nextEntities[0]?.id ?? "");
        } catch  {
        // persistFile displays the error.
        }
    }
    async function saveRelationships(nextRows) {
        const content = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeRelationships"])(nextRows);
        await persistFile("relationships.csv", content, "Đã lưu relationship và nguồn trực tiếp vào relationships.csv.");
        setRelationshipRows(nextRows);
        setEntities((current)=>{
            const referencedIds = new Set([
                ...aliasRows.map((item)=>item.entityId),
                ...nextRows.flatMap((item)=>[
                        item.fromEntityId,
                        item.toEntityId
                    ])
            ]);
            const nextEntities = current.filter((entity)=>entity.status !== "missing" || referencedIds.has(entity.id));
            referencedIds.forEach((entityId)=>{
                if (nextEntities.some((entity)=>entity.id === entityId)) return;
                const entityAliases = aliasRows.filter((item)=>item.entityId === entityId).map((item)=>item.alias);
                const relatedEdge = nextRows.find((item)=>item.fromEntityId === entityId || item.toEntityId === entityId);
                const relatedDefinition = relationshipDefinitions.find((item)=>item.type === relatedEdge?.relationship);
                const inferredType = relatedEdge?.fromEntityId === entityId ? relatedDefinition?.from : relatedDefinition?.to;
                nextEntities.push({
                    id: entityId,
                    name: entityAliases[0] ?? entityId,
                    type: inferredType ?? "Place",
                    status: "missing",
                    aliases: entityAliases,
                    properties: {},
                    sourceFile: "relationships.csv"
                });
            });
            return nextEntities;
        });
    }
    async function saveOntology(nextNodes, nextRelationships) {
        const ontologyContent = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeOntology"])(nextNodes, nextRelationships);
        const schemaContent = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeSchema"])(nextNodes, nextRelationships, datasetFiles["schema.yaml"]);
        await persistFiles({
            "ontology.yaml": ontologyContent,
            "schema.yaml": schemaContent
        }, "Đã lưu ontology.yaml và đồng bộ danh sách type trong schema.yaml.");
        setNodeDefinitions(nextNodes);
        setRelationshipDefinitions(nextRelationships);
    }
    function openEntity(entityId) {
        setSelectedId(entityId);
        setActiveTab("entities");
    }
    function openIssue(issue) {
        if (issue.entityId) {
            setSelectedId(issue.entityId);
        }
        setActiveTab(issue.target);
    }
    function resetDraft() {
        window.location.reload();
    }
    function runValidation() {
        setValidatedAt(new Date());
        setNotice(errorCount ? `Validation hoàn tất: ${errorCount} lỗi đang chặn publish.` : "Validation hoàn tất: dataset sẵn sàng để review.");
        setActiveTab("validation");
    }
    function handleImport(event) {
        const files = Array.from(event.target.files ?? []);
        if (!files.length) return;
        setImportedFiles(files.map((file)=>file.name));
        setNotice(`Đã chọn ${files.length} tệp cho draft import. Parser và API lưu dữ liệu chưa được kết nối.`);
        event.target.value = "";
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "kgPage",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "topbar kgTopbar",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Catalog intelligence"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 420,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                children: "Knowledge Graph"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 421,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgLead",
                                children: "Kiểm tra entity, alias và ontology trước khi dữ liệu được đưa vào Planner."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 422,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 419,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgHeaderActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                ref: importInputRef,
                                className: "kgFileInput",
                                type: "file",
                                accept: ".csv,.yaml,.yml",
                                multiple: true,
                                onChange: handleImport
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 427,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgSecondaryButton",
                                type: "button",
                                onClick: ()=>importInputRef.current?.click(),
                                children: "⇧ Import dataset"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 435,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: runValidation,
                                children: "✓ Validate graph"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 438,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 426,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 418,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                className: "kgSourceStrip",
                "aria-label": "Dataset source",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "kgPulse"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 446,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Local prototype snapshot"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 448,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: datasetLoading ? "Đang đọc dataset…" : "trung-temp/knowledge-graph · 6 files"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 449,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 447,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 445,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgSourceMeta",
                        children: [
                            importedFiles.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    importedFiles.length,
                                    " file chờ import"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 453,
                                columnNumber: 40
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Draft workspace"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 454,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                type: "button",
                                onClick: resetDraft,
                                children: "Tải lại từ file"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 455,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 452,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 444,
                columnNumber: 7
            }, this),
            notice && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgNotice",
                role: "status",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "i"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 461,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: notice
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 462,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        "aria-label": "Đóng thông báo",
                        onClick: ()=>setNotice(""),
                        children: "×"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 463,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 460,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                className: "metricGrid kgMetrics",
                "aria-label": "Knowledge graph metrics",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Entities"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 469,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: persistedCount
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 470,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    entities.filter((entity)=>entity.status === "missing").length,
                                    " tham chiếu chưa tồn tại"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 471,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 468,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Aliases"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 474,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: aliasRows.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 475,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: "Tiếng Việt và tiếng Anh"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 476,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 473,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Relationships"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 479,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: relationshipRows.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 480,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    relationshipDefinitions.length,
                                    " loại đã khai báo"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 481,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 478,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        className: errorCount ? "kgMetricDanger" : "",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Validation issues"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 484,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: issues.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 485,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    errorCount,
                                    " lỗi đang chặn publish"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 486,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 483,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 467,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("nav", {
                className: "kgWorkspaceTabs",
                "aria-label": "Knowledge graph sections",
                children: TABS.map((tab)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        className: activeTab === tab.id ? "active" : "",
                        onClick: ()=>setActiveTab(tab.id),
                        children: [
                            tab.label,
                            tab.id === "validation" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: issues.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 499,
                                columnNumber: 41
                            }, this)
                        ]
                    }, tab.id, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 492,
                        columnNumber: 11
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 490,
                columnNumber: 7
            }, this),
            activeTab === "entities" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "controlBar kgControlBar",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                className: "searchField",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "⌕"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 508,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: query,
                                        onChange: (event)=>setQuery(event.target.value),
                                        placeholder: "Tìm tên, entity ID hoặc alias…"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 509,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 507,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                value: typeFilter,
                                onChange: (event)=>setTypeFilter(event.target.value),
                                "aria-label": "Lọc loại entity",
                                children: TYPES.map((type)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: type,
                                        children: type === "all" ? "Mọi loại node" : type
                                    }, type, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 521,
                                        columnNumber: 17
                                    }, this))
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 515,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                value: statusFilter,
                                onChange: (event)=>setStatusFilter(event.target.value),
                                "aria-label": "Lọc trạng thái entity",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "all",
                                        children: "Mọi trạng thái"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 529,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "missing",
                                        children: "Thiếu entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 530,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "draft",
                                        children: "Bản nháp"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 531,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "verified",
                                        children: "Đã xác minh"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 532,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 524,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: ()=>beginAddEntity(),
                                children: "＋ Thêm entity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 534,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 506,
                        columnNumber: 11
                    }, this),
                    entityEditor !== null && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                        className: "kgInlineEditor kgEntityEditor",
                        onSubmit: submitEntity,
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Entity ID"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 542,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: entityDraft.id,
                                        disabled: entityEditor !== "new" && entities.some((item)=>item.id === entityEditor && item.status !== "missing"),
                                        onChange: (event)=>setEntityDraft((current)=>({
                                                    ...current,
                                                    id: event.target.value
                                                })),
                                        placeholder: "place_001"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 543,
                                        columnNumber: 17
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 541,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Canonical name"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 550,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: entityDraft.name,
                                        onChange: (event)=>setEntityDraft((current)=>({
                                                    ...current,
                                                    name: event.target.value
                                                })),
                                        placeholder: "Tên chuẩn"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 550,
                                        columnNumber: 49
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 550,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Node type"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 551,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                        value: entityDraft.type,
                                        onChange: (event)=>setEntityDraft((current)=>({
                                                    ...current,
                                                    type: event.target.value
                                                })),
                                        children: nodeDefinitions.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: node.type,
                                                children: node.type
                                            }, node.type, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 551,
                                                columnNumber: 202
                                            }, this))
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 551,
                                        columnNumber: 44
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 551,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Trạng thái"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 552,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                        value: entityDraft.status,
                                        onChange: (event)=>setEntityDraft((current)=>({
                                                    ...current,
                                                    status: event.target.value
                                                })),
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "draft",
                                                children: "Bản nháp"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 552,
                                                columnNumber: 176
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "verified",
                                                children: "Đã xác minh"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 552,
                                                columnNumber: 215
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 552,
                                        columnNumber: 45
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 552,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgEditorActions",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "kgQuietButton",
                                        type: "button",
                                        onClick: ()=>setEntityEditor(null),
                                        children: "Hủy"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 553,
                                        columnNumber: 48
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "kgPrimaryButton",
                                        type: "submit",
                                        disabled: saving,
                                        children: saving ? "Đang lưu…" : "Lưu entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 553,
                                        columnNumber: 146
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 553,
                                columnNumber: 15
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 540,
                        columnNumber: 13
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "dataLayout kgDataLayout",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "runList kgEntityList",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: [
                                                    filteredEntities.length,
                                                    " referenced entities"
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 560,
                                                columnNumber: 17
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                                children: "entities.csv: empty"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 561,
                                                columnNumber: 17
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 559,
                                        columnNumber: 15
                                    }, this),
                                    filteredEntities.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "emptyState",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                children: "Không tìm thấy entity"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 565,
                                                columnNumber: 19
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                children: "Thử đổi từ khóa hoặc bộ lọc hiện tại."
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 566,
                                                columnNumber: 19
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 564,
                                        columnNumber: 17
                                    }, this),
                                    filteredEntities.map((entity)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            type: "button",
                                            className: selectedId === entity.id ? "kgEntityCard active" : "kgEntityCard",
                                            onClick: ()=>setSelectedId(entity.id),
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "kgEntityCardTop",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: `kgNodeType kgNode-${entity.type.toLowerCase()}`,
                                                            children: entity.type
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 577,
                                                            columnNumber: 21
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: `status status-${entity.status === "missing" ? "failed" : entity.status}`,
                                                            children: STATUS_LABELS[entity.status]
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 578,
                                                            columnNumber: 21
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 576,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                                    children: entity.name
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 582,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: entity.id
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 583,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    children: [
                                                        entity.aliases.length,
                                                        " alias · nguồn ",
                                                        entity.sourceFile
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 584,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, entity.id, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 570,
                                            columnNumber: 17
                                        }, this))
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 558,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "detailPane kgInspector",
                                children: selectedEntity ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(EntityInspector, {
                                    entity: selectedEntity,
                                    issues: issues.filter((issue)=>issue.entityId === selectedEntity.id),
                                    onCreate: ()=>beginAddEntity(selectedEntity),
                                    onEdit: ()=>beginEditEntity(selectedEntity),
                                    onDelete: ()=>deleteEntity(selectedEntity)
                                }, void 0, false, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 591,
                                    columnNumber: 17
                                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "detailEmpty",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                            children: "Chọn một entity để kiểm tra"
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 600,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            children: "Alias, properties và raw record sẽ xuất hiện tại đây."
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 601,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 599,
                                    columnNumber: 17
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 589,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 557,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true),
            activeTab === "aliases" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(AliasTable, {
                aliases: aliasRows,
                entities: entities,
                saving: saving,
                onOpenEntity: openEntity,
                onSave: saveAliases
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 610,
                columnNumber: 9
            }, this),
            activeTab === "relationships" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RelationshipTable, {
                relationships: relationshipRows,
                definitions: relationshipDefinitions,
                saving: saving,
                onSave: saveRelationships
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 620,
                columnNumber: 9
            }, this),
            activeTab === "ontology" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(OntologyTable, {
                nodes: nodeDefinitions,
                relationships: relationshipDefinitions,
                rawSchema: datasetFiles["schema.yaml"],
                saving: saving,
                onSave: saveOntology
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 629,
                columnNumber: 9
            }, this),
            activeTab === "validation" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                className: "kgPanel",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                        className: "kgPanelHeader",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        className: "eyebrow",
                                        children: "Contract health"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 642,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                        children: "Validation report"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 643,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: validatedAt ? `Kiểm tra gần nhất lúc ${validatedAt.toLocaleTimeString("vi-VN")}` : "Kết quả tự động từ snapshot đang mở."
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 644,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 641,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: runValidation,
                                children: "↻ Chạy lại"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 650,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 640,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgValidationSummary",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgHealthScore",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                        children: Math.max(0, 100 - errorCount * 18 - (issues.length - errorCount) * 4)
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 653,
                                        columnNumber: 44
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "/ 100"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 653,
                                        columnNumber: 132
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 653,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Dataset chưa sẵn sàng để publish"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 654,
                                        columnNumber: 18
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: "Xử lý lỗi contract trước, sau đó review các cảnh báo về độ đầy đủ dữ liệu."
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 654,
                                        columnNumber: 57
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 654,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "status status-failed",
                                children: [
                                    errorCount,
                                    " blocking"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 655,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 652,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgIssueList",
                        children: issues.map((issue)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                type: "button",
                                onClick: ()=>openIssue(issue),
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        className: `kgIssueIcon kgIssue-${issue.severity}`,
                                        children: issue.severity === "error" ? "!" : issue.severity === "warning" ? "△" : "i"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 660,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                children: issue.title
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 661,
                                                columnNumber: 22
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                children: issue.message
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 661,
                                                columnNumber: 42
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: issue.path
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 661,
                                                columnNumber: 64
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 661,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        className: `status status-${issue.severity === "error" ? "failed" : "warning"}`,
                                        children: severityLabel(issue.severity)
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 662,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
                                        children: "→"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 663,
                                        columnNumber: 17
                                    }, this)
                                ]
                            }, issue.id, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 659,
                                columnNumber: 15
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 657,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 639,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("footer", {
                className: "kgFooter",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: "Snapshot này chỉ phục vụ giao diện quản trị. Dữ liệu chưa được ghi vào PostgreSQL, Place Resolver hoặc các file nguồn cho đến khi có API admin tương ứng."
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 671,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        disabled: true,
                        title: "Cần xử lý validation issues và kết nối API lưu draft",
                        children: "Publish version"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 675,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 670,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 417,
        columnNumber: 5
    }, this);
}
function AliasTable({ aliases, entities, saving, onOpenEntity, onSave }) {
    const [editingIndex, setEditingIndex] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [entityId, setEntityId] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [aliasValue, setAliasValue] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [formError, setFormError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    function beginEdit(index) {
        setEditingIndex(index);
        setEntityId(aliases[index].entityId);
        setAliasValue(aliases[index].alias);
        setFormError("");
    }
    function beginAdd() {
        setEditingIndex("new");
        setEntityId("");
        setAliasValue("");
        setFormError("");
    }
    async function submit(event) {
        event.preventDefault();
        if (!entityId.trim() || !aliasValue.trim()) {
            setFormError("Entity ID và alias là bắt buộc.");
            return;
        }
        const nextRow = {
            entityId: entityId.trim(),
            alias: aliasValue.trim(),
            language: /[À-ỹ]/u.test(aliasValue) ? "vi" : "en"
        };
        const nextRows = editingIndex === "new" ? [
            ...aliases,
            nextRow
        ] : aliases.map((item, index)=>index === editingIndex ? nextRow : item);
        try {
            await onSave(nextRows);
            setEditingIndex(null);
        } catch  {
        // The parent displays the API error.
        }
    }
    async function removeAlias(index) {
        const item = aliases[index];
        if (!window.confirm(`Xóa alias “${item.alias}” khỏi aliases.csv?`)) return;
        try {
            await onSave(aliases.filter((_, itemIndex)=>itemIndex !== index));
            if (editingIndex === index) setEditingIndex(null);
        } catch  {
        // The parent displays the API error.
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "kgPanel kgTablePanel",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "kgPanelHeader",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Identity resolution"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 752,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "Aliases"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 753,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Mỗi alias là một dòng và được lưu trực tiếp vào aliases.csv."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 754,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 751,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgPanelActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "status status-warning",
                                children: [
                                    aliases.length,
                                    " records"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 757,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: beginAdd,
                                children: "＋ Thêm alias"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 758,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 756,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 750,
                columnNumber: 7
            }, this),
            editingIndex !== null && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                className: "kgInlineEditor kgAliasEditor",
                onSubmit: submit,
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Entity ID"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 763,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: entityId,
                                onChange: (event)=>setEntityId(event.target.value),
                                placeholder: "place_001"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 763,
                                columnNumber: 40
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 763,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Alias"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 764,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: aliasValue,
                                onChange: (event)=>setAliasValue(event.target.value),
                                placeholder: "Tên địa điểm"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 764,
                                columnNumber: 36
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 764,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgEditorActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgQuietButton",
                                type: "button",
                                onClick: ()=>setEditingIndex(null),
                                children: "Hủy"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 766,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "submit",
                                disabled: saving,
                                children: saving ? "Đang lưu…" : "Lưu vào file"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 767,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 765,
                        columnNumber: 11
                    }, this),
                    formError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: formError
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 769,
                        columnNumber: 25
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 762,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgTableScroll",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
                    className: "kgTable",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Alias"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 774,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Ngôn ngữ"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 774,
                                        columnNumber: 36
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Entity ID"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 774,
                                        columnNumber: 53
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 774,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Thao tác"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 774,
                                        columnNumber: 86
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 774,
                                columnNumber: 18
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 774,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                            children: aliases.map((alias, index)=>{
                                const entity = entities.find((item)=>item.id === alias.entityId);
                                return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                                children: alias.alias
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 780,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 780,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgLanguage",
                                                children: alias.language.toUpperCase()
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 781,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 781,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: alias.entityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 782,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 782,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: `status status-${entity?.status === "missing" ? "failed" : "draft"}`,
                                                children: entity?.status === "missing" ? "Không tồn tại" : "Draft"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 783,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 783,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                className: "kgRowActions",
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        type: "button",
                                                        onClick: ()=>beginEdit(index),
                                                        children: "Sửa"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 784,
                                                        columnNumber: 53
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        type: "button",
                                                        onClick: ()=>onOpenEntity(alias.entityId),
                                                        children: "Mở"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 784,
                                                        columnNumber: 120
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        className: "danger",
                                                        type: "button",
                                                        onClick: ()=>removeAlias(index),
                                                        children: "Xóa"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 784,
                                                        columnNumber: 198
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 784,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 784,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, `${alias.entityId}-${alias.alias}-${index}`, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 779,
                                    columnNumber: 17
                                }, this);
                            })
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 775,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 773,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 772,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 749,
        columnNumber: 5
    }, this);
}
function RelationshipTable({ relationships, definitions, saving, onSave }) {
    const [editingIndex, setEditingIndex] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [draft, setDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({
        fromEntityId: "",
        relationship: "LOCATED_IN",
        toEntityId: "",
        source: ""
    });
    const [formError, setFormError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    function beginEdit(index) {
        const item = relationships[index];
        setEditingIndex(index);
        setDraft({
            fromEntityId: item.fromEntityId,
            relationship: item.relationship,
            toEntityId: item.toEntityId,
            source: item.source
        });
        setFormError("");
    }
    function beginAdd() {
        setEditingIndex("new");
        setDraft({
            fromEntityId: "",
            relationship: definitions[0]?.type ?? "LOCATED_IN",
            toEntityId: "",
            source: ""
        });
        setFormError("");
    }
    async function submit(event) {
        event.preventDefault();
        if (editingIndex === null) return;
        if (!draft.fromEntityId.trim() || !draft.toEntityId.trim() || !draft.source.trim()) {
            setFormError("Entity nguồn, entity đích và nguồn dữ liệu là bắt buộc.");
            return;
        }
        const nextRow = {
            id: editingIndex === "new" ? `relationship-${Date.now()}` : relationships[editingIndex].id,
            fromEntityId: draft.fromEntityId.trim(),
            relationship: draft.relationship,
            toEntityId: draft.toEntityId.trim(),
            source: draft.source.trim()
        };
        const nextRows = editingIndex === "new" ? [
            ...relationships,
            nextRow
        ] : relationships.map((item, index)=>index === editingIndex ? nextRow : item);
        try {
            await onSave(nextRows);
            setEditingIndex(null);
        } catch  {
        // The parent displays the API error.
        }
    }
    async function removeRelationship(index) {
        const item = relationships[index];
        if (!window.confirm(`Xóa relationship ${item.fromEntityId} —${item.relationship}→ ${item.toEntityId}?`)) return;
        try {
            await onSave(relationships.filter((_, itemIndex)=>itemIndex !== index));
            if (editingIndex === index) setEditingIndex(null);
        } catch  {
        // The parent displays the API error.
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "kgPanel kgTablePanel",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "kgPanelHeader",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Graph edges"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 863,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "Relationships"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 864,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Mỗi relationship là một dòng; cột nguồn được lưu cùng cạnh dữ liệu."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 865,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 862,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgPanelActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: `status status-${relationships.length ? "completed" : "warning"}`,
                                children: [
                                    relationships.length,
                                    " records"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 868,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: beginAdd,
                                children: "＋ Thêm relationship"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 869,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 867,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 861,
                columnNumber: 7
            }, this),
            editingIndex !== null && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                className: "kgInlineEditor kgRelationshipEditor",
                onSubmit: submit,
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "From entity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 874,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: draft.fromEntityId,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            fromEntityId: event.target.value
                                        })),
                                placeholder: "place_001"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 874,
                                columnNumber: 42
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 874,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Relationship"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 875,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                value: draft.relationship,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            relationship: event.target.value
                                        })),
                                children: definitions.map((definition)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: definition.type,
                                        children: definition.type
                                    }, definition.type, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 875,
                                        columnNumber: 207
                                    }, this))
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 875,
                                columnNumber: 43
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 875,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "To entity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 876,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: draft.toEntityId,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            toEntityId: event.target.value
                                        })),
                                placeholder: "city_001"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 876,
                                columnNumber: 40
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 876,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Nguồn"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 877,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: draft.source,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            source: event.target.value
                                        })),
                                placeholder: "Google Maps URL hoặc dataset"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 877,
                                columnNumber: 36
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 877,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgEditorActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgQuietButton",
                                type: "button",
                                onClick: ()=>setEditingIndex(null),
                                children: "Hủy"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 879,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "submit",
                                disabled: saving,
                                children: saving ? "Đang lưu…" : "Lưu vào file"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 880,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 878,
                        columnNumber: 11
                    }, this),
                    formError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: formError
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 882,
                        columnNumber: 25
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 873,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgTableScroll",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
                    className: "kgTable kgRelationshipTable",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "From"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 887,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Relationship"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 887,
                                        columnNumber: 35
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "To"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 887,
                                        columnNumber: 56
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Nguồn"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 887,
                                        columnNumber: 67
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Thao tác"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 887,
                                        columnNumber: 81
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 887,
                                columnNumber: 18
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 887,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                            children: relationships.length === 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                className: "kgEmptyRow",
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                    colSpan: 5,
                                    children: "relationships.csv chưa có bản ghi. Bấm “Thêm relationship” để tạo dòng đầu tiên."
                                }, void 0, false, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 890,
                                    columnNumber: 42
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 890,
                                columnNumber: 15
                            }, this) : relationships.map((relationship, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: relationship.fromEntityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 893,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 893,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgRelationBadge",
                                                children: relationship.relationship
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 894,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 894,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: relationship.toEntityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 895,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 895,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgSourceCell",
                                                title: relationship.source,
                                                children: relationship.source
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 896,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 896,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                className: "kgRowActions",
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        type: "button",
                                                        onClick: ()=>beginEdit(index),
                                                        children: "Sửa"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 897,
                                                        columnNumber: 51
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        className: "danger",
                                                        type: "button",
                                                        onClick: ()=>removeRelationship(index),
                                                        children: "Xóa"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 897,
                                                        columnNumber: 118
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 897,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 897,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, relationship.id, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 892,
                                    columnNumber: 15
                                }, this))
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 888,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 886,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 885,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 860,
        columnNumber: 5
    }, this);
}
function OntologyTable({ nodes, relationships, rawSchema, saving, onSave }) {
    const [editingKey, setEditingKey] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [draft, setDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({
        name: "",
        description: "",
        from: "",
        to: ""
    });
    const [formError, setFormError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    function addNode() {
        setEditingKey("new-node");
        setDraft({
            name: "",
            description: "",
            from: "",
            to: ""
        });
        setFormError("");
    }
    function addRelationship() {
        setEditingKey("new-relationship");
        setDraft({
            name: "",
            description: "",
            from: "",
            to: ""
        });
        setFormError("");
    }
    function editNode(node) {
        setEditingKey(`node:${node.type}`);
        setDraft({
            name: node.type,
            description: node.description ?? "",
            from: "",
            to: ""
        });
        setFormError("");
    }
    function editRelationship(relationship) {
        setEditingKey(`relationship:${relationship.type}`);
        setDraft({
            name: relationship.type,
            description: relationship.description,
            from: relationship.from ?? "",
            to: relationship.to ?? ""
        });
        setFormError("");
    }
    async function submit(event) {
        event.preventDefault();
        if (!draft.name.trim()) {
            setFormError("Tên node hoặc relationship là bắt buộc.");
            return;
        }
        const normalizedName = draft.name.trim();
        if (editingKey.startsWith("new-") && [
            ...nodes.map((item)=>String(item.type)),
            ...relationships.map((item)=>String(item.type))
        ].some((item)=>item === normalizedName)) {
            setFormError(`${normalizedName} đã tồn tại trong ontology.`);
            return;
        }
        const [kind, name] = editingKey.split(":");
        let nextNodes = kind === "node" ? nodes.map((node)=>node.type === name ? {
                ...node,
                description: draft.description.trim() || null
            } : node) : nodes;
        let nextRelationships = kind === "relationship" ? relationships.map((relationship)=>relationship.type === name ? {
                ...relationship,
                from: draft.from || null,
                to: draft.to || null,
                description: draft.description.trim()
            } : relationship) : relationships;
        if (editingKey === "new-node") {
            nextNodes = [
                ...nodes,
                {
                    type: normalizedName,
                    description: draft.description.trim() || null
                }
            ];
        }
        if (editingKey === "new-relationship") {
            nextRelationships = [
                ...relationships,
                {
                    type: normalizedName,
                    from: draft.from || null,
                    to: draft.to || null,
                    description: draft.description.trim()
                }
            ];
        }
        try {
            await onSave(nextNodes, nextRelationships);
            setEditingKey("");
        } catch  {
        // The parent displays the API error.
        }
    }
    async function removeNode(node) {
        if (!window.confirm(`Xóa node type ${node.type} khỏi ontology.yaml và schema.yaml?`)) return;
        try {
            await onSave(nodes.filter((item)=>item.type !== node.type), relationships);
            if (editingKey === `node:${node.type}`) setEditingKey("");
        } catch  {
        // The parent displays the API error.
        }
    }
    async function removeOntologyRelationship(relationship) {
        if (!window.confirm(`Xóa relationship type ${relationship.type} khỏi ontology.yaml và schema.yaml?`)) return;
        try {
            await onSave(nodes, relationships.filter((item)=>item.type !== relationship.type));
            if (editingKey === `relationship:${relationship.type}`) setEditingKey("");
        } catch  {
        // The parent displays the API error.
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "kgPanel kgTablePanel",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "kgPanelHeader",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Domain contract"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1017,
                                columnNumber: 14
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "Schema & Ontology"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1017,
                                columnNumber: 56
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Mỗi node hoặc relationship type là một dòng compact."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1017,
                                columnNumber: 82
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1017,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgPanelActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "status status-draft",
                                children: "ontology.yaml"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1018,
                                columnNumber: 41
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgSecondaryButton",
                                type: "button",
                                onClick: addNode,
                                children: "＋ Node"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1018,
                                columnNumber: 99
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: addRelationship,
                                children: "＋ Relationship"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1018,
                                columnNumber: 184
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1018,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1016,
                columnNumber: 7
            }, this),
            editingKey && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                className: "kgInlineEditor kgOntologyEditor",
                onSubmit: submit,
                children: [
                    editingKey.startsWith("new-") && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Tên type"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1022,
                                columnNumber: 52
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: draft.name,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            name: event.target.value
                                        })),
                                placeholder: editingKey === "new-node" ? "Attraction" : "HAS_CATEGORY"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1022,
                                columnNumber: 73
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1022,
                        columnNumber: 45
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Mô tả"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1023,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: draft.description,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            description: event.target.value
                                        })),
                                placeholder: "Mô tả nghiệp vụ"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1023,
                                columnNumber: 36
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1023,
                        columnNumber: 11
                    }, this),
                    (editingKey.startsWith("relationship:") || editingKey === "new-relationship") && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "From type"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1025,
                                        columnNumber: 20
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                        value: draft.from,
                                        onChange: (event)=>setDraft((current)=>({
                                                    ...current,
                                                    from: event.target.value
                                                })),
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "",
                                                children: "Chưa xác định"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1025,
                                                columnNumber: 157
                                            }, this),
                                            nodes.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                    value: node.type,
                                                    children: node.type
                                                }, node.type, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1025,
                                                    columnNumber: 217
                                                }, this))
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1025,
                                        columnNumber: 42
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1025,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "To type"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1026,
                                        columnNumber: 20
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                        value: draft.to,
                                        onChange: (event)=>setDraft((current)=>({
                                                    ...current,
                                                    to: event.target.value
                                                })),
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "",
                                                children: "Chưa xác định"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1026,
                                                columnNumber: 151
                                            }, this),
                                            nodes.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                    value: node.type,
                                                    children: node.type
                                                }, node.type, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1026,
                                                    columnNumber: 211
                                                }, this))
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1026,
                                        columnNumber: 40
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1026,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgEditorActions",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgQuietButton",
                                type: "button",
                                onClick: ()=>setEditingKey(""),
                                children: "Hủy"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1028,
                                columnNumber: 44
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "submit",
                                disabled: saving,
                                children: saving ? "Đang lưu…" : "Lưu ontology"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1028,
                                columnNumber: 138
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1028,
                        columnNumber: 11
                    }, this),
                    formError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: formError
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1029,
                        columnNumber: 25
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1021,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgTableScroll",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
                    className: "kgTable kgOntologyTable",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Loại"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Tên"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 35
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "From"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 47
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "To"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 60
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Mô tả"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Trạng thái"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 85
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Thao tác"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1034,
                                        columnNumber: 104
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1034,
                                columnNumber: 18
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1034,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                            children: [
                                nodes.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgLanguage",
                                                    children: "NODE"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1036,
                                                    columnNumber: 68
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 64
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                                    children: node.type
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1036,
                                                    columnNumber: 117
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 113
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: "—"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 150
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: "—"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 160
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: node.description ?? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgMissingText",
                                                    children: "Chưa có mô tả"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1036,
                                                    columnNumber: 195
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 170
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: `status status-${node.description ? "completed" : "warning"}`,
                                                    children: node.description ? "Defined" : "Missing"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1036,
                                                    columnNumber: 257
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 253
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "kgRowActions",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            type: "button",
                                                            onClick: ()=>editNode(node),
                                                            children: "Sửa"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1036,
                                                            columnNumber: 425
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            className: "danger",
                                                            type: "button",
                                                            onClick: ()=>removeNode(node),
                                                            children: "Xóa"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1036,
                                                            columnNumber: 490
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1036,
                                                    columnNumber: 395
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1036,
                                                columnNumber: 391
                                            }, this)
                                        ]
                                    }, `node-${node.type}`, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1036,
                                        columnNumber: 34
                                    }, this)),
                                relationships.map((relationship)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgLanguage",
                                                    children: "EDGE"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1037,
                                                    columnNumber: 100
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 96
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: relationship.type
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1037,
                                                    columnNumber: 149
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 145
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: relationship.from ?? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgMissingText",
                                                    children: "?"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1037,
                                                    columnNumber: 212
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 186
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: relationship.to ?? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgMissingText",
                                                    children: "?"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1037,
                                                    columnNumber: 282
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 258
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: relationship.description
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 328
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: `status status-${relationship.from && relationship.to ? "completed" : "failed"}`,
                                                    children: relationship.from && relationship.to ? "Defined" : "Incomplete"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1037,
                                                    columnNumber: 367
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 363
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "kgRowActions",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            type: "button",
                                                            onClick: ()=>editRelationship(relationship),
                                                            children: "Sửa"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1037,
                                                            columnNumber: 577
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            className: "danger",
                                                            type: "button",
                                                            onClick: ()=>removeOntologyRelationship(relationship),
                                                            children: "Xóa"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1037,
                                                            columnNumber: 658
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1037,
                                                    columnNumber: 547
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1037,
                                                columnNumber: 543
                                            }, this)
                                        ]
                                    }, `relationship-${relationship.type}`, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1037,
                                        columnNumber: 50
                                    }, this))
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1035,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1033,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1032,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("details", {
                className: "kgSchemaDetails",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("summary", {
                        children: "Xem schema.yaml"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1041,
                        columnNumber: 44
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RawFile, {
                        name: "schema.yaml",
                        value: rawSchema
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1041,
                        columnNumber: 78
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1041,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1015,
        columnNumber: 5
    }, this);
}
function EntityInspector({ entity, issues, onCreate, onEdit, onDelete }) {
    const [tab, setTab] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("overview");
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "detailHeader kgInspectorHeader",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Referenced entity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1065,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: entity.name
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1066,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: [
                                    entity.id,
                                    " · nguồn ",
                                    entity.sourceFile
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1067,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1064,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: `status status-${entity.status === "missing" ? "failed" : entity.status}`,
                        children: STATUS_LABELS[entity.status]
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1069,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1063,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgInspectorActions",
                children: entity.status === "missing" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                            className: "kgMissingHint",
                            children: "Entity chưa có record trong entities.csv"
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1074,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            className: "kgPrimaryButton",
                            type: "button",
                            onClick: onCreate,
                            children: "＋ Tạo entity"
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1074,
                            columnNumber: 92
                        }, this)
                    ]
                }, void 0, true) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            className: "kgSecondaryButton",
                            type: "button",
                            onClick: onEdit,
                            children: "Chỉnh sửa"
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1076,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            className: "kgDangerButton",
                            type: "button",
                            onClick: onDelete,
                            children: "Xóa"
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1076,
                            columnNumber: 100
                        }, this)
                    ]
                }, void 0, true)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1072,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "tabList kgInspectorTabs",
                role: "tablist",
                children: [
                    "overview",
                    "aliases",
                    "relations",
                    "raw"
                ].map((item)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        className: tab === item ? "active" : "",
                        onClick: ()=>setTab(item),
                        children: item === "overview" ? "Overview" : item === "aliases" ? `Aliases (${entity.aliases.length})` : item === "relations" ? "Relations (0)" : "Raw data"
                    }, item, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1082,
                        columnNumber: 11
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1080,
                columnNumber: 7
            }, this),
            tab === "overview" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgInspectorBody",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "runFacts kgEntityFacts",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: "Canonical ID"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1091,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                        children: entity.id
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1091,
                                        columnNumber: 46
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1091,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: "Node type"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1092,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: entity.type
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1092,
                                        columnNumber: 43
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1092,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: "Properties"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1093,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: Object.keys(entity.properties).length
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1093,
                                        columnNumber: 44
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1093,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: "Relations"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1094,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "0"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1094,
                                        columnNumber: 43
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1094,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1090,
                        columnNumber: 11
                    }, this),
                    issues.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgInlineIssues",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                children: "Validation issues"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1098,
                                columnNumber: 15
                            }, this),
                            issues.map((issue)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            children: "!"
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1099,
                                            columnNumber: 56
                                        }, this),
                                        issue.message
                                    ]
                                }, issue.id, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 1099,
                                    columnNumber: 38
                                }, this))
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1097,
                        columnNumber: 13
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "kgDefinitionList",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                children: "Identity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1103,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dl", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Canonical name"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1105,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: entity.name
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1105,
                                                columnNumber: 43
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1105,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Status"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1106,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: STATUS_LABELS[entity.status]
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1106,
                                                columnNumber: 35
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1106,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Source"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1107,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: entity.sourceFile
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1107,
                                                    columnNumber: 39
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1107,
                                                columnNumber: 35
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1107,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Provenance"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1108,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: "Chưa được khai báo"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1108,
                                                columnNumber: 39
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1108,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1104,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1102,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1089,
                columnNumber: 9
            }, this),
            tab === "aliases" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAliasCards",
                children: entity.aliases.map((alias, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: index + 1
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1117,
                                columnNumber: 34
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: alias
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1117,
                                        columnNumber: 63
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: alias === "Hoan Kiem Lake" ? "English" : "Vietnamese"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1117,
                                        columnNumber: 77
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1117,
                                columnNumber: 58
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                children: "aliases.csv"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1117,
                                columnNumber: 153
                            }, this)
                        ]
                    }, alias, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1117,
                        columnNumber: 13
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1115,
                columnNumber: 9
            }, this),
            tab === "relations" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgInspectorEmpty",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "◇"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1123,
                        columnNumber: 43
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                        children: "Chưa có relationship"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1123,
                        columnNumber: 57
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: "Entity này chưa được nối với node nào khác."
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1123,
                        columnNumber: 84
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1123,
                columnNumber: 9
            }, this),
            tab === "raw" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RawFile, {
                name: entity.sourceFile,
                value: __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["rawDataset"][entity.sourceFile] ?? ""
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1126,
                columnNumber: 25
            }, this)
        ]
    }, void 0, true);
}
function RawFile({ name, value }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
        className: "kgRawFile",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: name
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1134,
                        columnNumber: 15
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                        children: value ? `${value.split("\n").length} lines` : "EMPTY"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1134,
                        columnNumber: 34
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1134,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("pre", {
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                    children: value || "// File is empty"
                }, void 0, false, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1135,
                    columnNumber: 12
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1135,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1133,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=_a877fabc._.js.map