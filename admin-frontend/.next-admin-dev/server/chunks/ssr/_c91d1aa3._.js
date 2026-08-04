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
    "parseNodeTypeDefinitions",
    ()=>parseNodeTypeDefinitions,
    "parseOntology",
    ()=>parseOntology,
    "parseProperties",
    ()=>parseProperties,
    "parseRelationships",
    ()=>parseRelationships,
    "rawDataset",
    ()=>rawDataset,
    "resolveNodeTypeProperties",
    ()=>resolveNodeTypeProperties,
    "serializeAliases",
    ()=>serializeAliases,
    "serializeEntities",
    ()=>serializeEntities,
    "serializeOntology",
    ()=>serializeOntology,
    "serializeProperties",
    ()=>serializeProperties,
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
        type: "TravelPlace",
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
        type: "TravelPlace",
        description: "Điểm tham quan, di tích lịch sử, danh thắng tự nhiên và khu trải nghiệm du lịch"
    },
    {
        type: "Restaurant",
        description: "Nhà hàng, quán ăn phục vụ bữa chính"
    },
    {
        type: "DrinkDessert",
        description: "Quán nước, quán cà phê, tiệm trà sữa, tiệm chè, bánh ngọt và đồ ăn vặt tráng miệng"
    },
    {
        type: "Accommodation",
        description: "Cơ sở lưu trú du lịch (khách sạn, resort, homestay, villa, nhà nghỉ)"
    },
    {
        type: "Area",
        description: "Khu vực địa lý ở bất kỳ cấp nào"
    },
    {
        type: "Activity",
        description: "Hoạt động hoặc trải nghiệm du lịch như săn mây hoặc thưởng thức cà phê trứng"
    }
];
const ontologyRelationships = [
    {
        type: "LOCATED_IN",
        from: "Place",
        to: "Area",
        description: "Một địa điểm hoặc khu vực nằm trong một khu vực hành chính khác"
    },
    {
        type: "NEAR",
        from: "Place",
        to: "Place",
        description: "Khoảng cách lân cận gần kề giữa hai địa điểm du lịch / cơ sở dịch vụ"
    },
    {
        type: "PART_OF",
        from: "LocationEntity",
        to: "LocationEntity",
        description: "Địa điểm thành phần thuộc một quần thể danh thắng hoặc cụm du lịch lớn hơn"
    },
    {
        type: "CONNECTS_TO",
        from: "Place",
        to: "Place",
        description: "Có tuyến hoặc chặng di chuyển trực tiếp giữa hai địa điểm"
    },
    {
        type: "RECOMMENDS",
        from: "Area",
        to: "Place|Activity",
        description: "Khu vực hành chính đề xuất địa điểm hoặc cơ sở dịch vụ theo ngữ cảnh có nguồn"
    },
    {
        type: "OFFERS_ACTIVITY",
        from: "Place",
        to: "Activity",
        description: "Địa điểm cung cấp hoặc là nơi thực hiện một hoạt động du lịch"
    }
];
const rawDataset = {
    "aliases.csv": "entity_id,alias\nplace_001,Hồ Hoàn Kiếm\nplace_001,Hoan Kiem Lake\nrestaurant_001,Bún Chả Obama",
    "entities.csv": "id,name,type,status\n",
    "ontology.yaml": "TravelPlace:\n  description: Điểm tham quan\n\nArea:\n  description: Khu vực địa lý\n\nLOCATED_IN:\n  from: Place\n  to: Area",
    "properties.csv": "entity_id,key,value,source\n",
    "relationships.csv": "id,from_entity_id,relationship,to_entity_id,recommendations,source\n",
    "schema.yaml": "nodes:\n  - TravelPlace\n  - Area\n\nrelationships:\n  - LOCATED_IN\n\nnode_type_definitions:\n  Entity:\n    abstract: true\n  LocationEntity:\n    abstract: true\n    extends: Entity\n  Place:\n    abstract: true\n    extends: LocationEntity\n  TravelPlace:\n    extends: Place\n  Area:\n    extends: LocationEntity"
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
function parseProperties(content) {
    return parseCsvRows(content).slice(1).filter((row)=>row[0]?.trim() && row[1]?.trim()).map((row)=>({
            entityId: row[0].trim(),
            key: row[1].trim(),
            value: row[2]?.trim() ?? "",
            source: row[3]?.trim() ?? ""
        }));
}
function serializeProperties(items) {
    return [
        "entity_id,key,value,source",
        ...items.map((item)=>[
                item.entityId,
                item.key,
                item.value,
                item.source
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
    const rows = parseCsvRows(content);
    const header = rows[0] ?? [];
    const indexOf = (name)=>header.indexOf(name);
    const modern = indexOf("id") >= 0;
    return rows.slice(1).filter((row)=>{
        const offset = modern ? 1 : 0;
        return row[offset]?.trim() && row[offset + 1]?.trim() && row[offset + 2]?.trim();
    }).map((row, index)=>{
        const fromEntityId = row[indexOf("from_entity_id") >= 0 ? indexOf("from_entity_id") : 0]?.trim() ?? "";
        const relationship = row[indexOf("relationship") >= 0 ? indexOf("relationship") : 1]?.trim() ?? "";
        const toEntityId = row[indexOf("to_entity_id") >= 0 ? indexOf("to_entity_id") : 2]?.trim() ?? "";
        return {
            id: modern ? row[indexOf("id")].trim() : `relationship-${index}-${fromEntityId}-${toEntityId}`,
            fromEntityId,
            relationship,
            toEntityId,
            recommendations: indexOf("recommendations") >= 0 ? row[indexOf("recommendations")]?.trim() ?? "[]" : "[]",
            source: row[indexOf("source") >= 0 ? indexOf("source") : 3]?.trim() ?? ""
        };
    });
}
function serializeRelationships(items) {
    return [
        "id,from_entity_id,relationship,to_entity_id,recommendations,source",
        ...items.map((item)=>[
                item.id,
                item.fromEntityId,
                item.relationship,
                item.toEntityId,
                item.recommendations,
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
    const replaceList = (content, section, values)=>{
        const block = [
            `${section}:`,
            ...values.map((value)=>`  - ${value}`)
        ].join("\n");
        const pattern = new RegExp(`^${section}:\\s*\\n(?:[ \\t]+-[^\\n]+\\n?)*`, "m");
        return pattern.test(content) ? content.replace(pattern, `${block}\n`) : `${block}\n\n${content}`;
    };
    return replaceList(replaceList(currentSchema, "nodes", nodes.map((node)=>node.type)), "relationships", relationships.map((relationship)=>relationship.type)).trim();
}
function parseNodeTypeDefinitions(content) {
    const definitions = {};
    let inSection = false;
    let current = "";
    let activeList = null;
    const parseList = (rawValue)=>rawValue.replace(/^\[/, "").replace(/\]$/, "").split(",").map((value)=>value.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);
    for (const line of content.split(/\r?\n/)){
        if (!inSection) {
            if (/^node_type_definitions:\s*$/.test(line)) inSection = true;
            continue;
        }
        if (/^\S/.test(line)) break;
        if (!line.trim() || /^\s+#/.test(line)) continue;
        const typeMatch = line.match(/^  ([A-Za-z][A-Za-z0-9_]*):\s*$/);
        if (typeMatch) {
            current = typeMatch[1];
            activeList = null;
            definitions[current] = {
                abstract: false,
                extends: null,
                requiredProperties: [],
                optionalProperties: []
            };
            continue;
        }
        if (!current) continue;
        const listItem = line.match(/^      -\s*(.+?)\s*$/);
        if (listItem && activeList) {
            definitions[current][activeList].push(listItem[1].trim().replace(/^['"]|['"]$/g, ""));
            continue;
        }
        const field = line.match(/^    ([a-z_]+):\s*(.*)$/);
        if (!field) continue;
        const [, key, rawValue] = field;
        activeList = null;
        if (key === "abstract") definitions[current].abstract = rawValue.trim() === "true";
        if (key === "extends") definitions[current].extends = rawValue.trim() || null;
        if (key === "required_properties") {
            definitions[current].requiredProperties = parseList(rawValue);
            if (!rawValue.trim()) activeList = "requiredProperties";
        }
        if (key === "optional_properties") {
            definitions[current].optionalProperties = parseList(rawValue);
            if (!rawValue.trim()) activeList = "optionalProperties";
        }
    }
    return definitions;
}
function typeLineage(type, definitions) {
    const lineage = new Set();
    let current = type;
    while(current && !lineage.has(current)){
        lineage.add(current);
        current = definitions[current]?.extends ?? null;
    }
    return lineage;
}
function resolveNodeTypeProperties(type, definitions) {
    const required = new Set();
    const optional = new Set();
    for (const current of typeLineage(type, definitions)){
        definitions[current]?.requiredProperties.forEach((property)=>required.add(property));
        definitions[current]?.optionalProperties.forEach((property)=>optional.add(property));
    }
    required.forEach((property)=>optional.delete(property));
    return {
        requiredProperties: [
            ...required
        ].sort(),
        optionalProperties: [
            ...optional
        ].sort()
    };
}
function validateKnowledgeGraph(entities, relationships = [], nodes = ontologyNodes, relationshipDefinitions = ontologyRelationships, nodeTypeDefinitions = {}) {
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
    if (!persistedEntities.some((entity)=>Object.keys(entity.properties).length > 0)) {
        issues.push({
            id: "properties-empty",
            severity: "warning",
            title: "Chưa có properties",
            message: "properties.csv đang rỗng; entity chưa có thuộc tính nghiệp vụ.",
            path: "properties.csv",
            target: "entities"
        });
    }
    persistedEntities.forEach((entity)=>{
        const required = new Set();
        typeLineage(entity.type, nodeTypeDefinitions).forEach((type)=>{
            nodeTypeDefinitions[type]?.requiredProperties.forEach((property)=>required.add(property));
        });
        const missing = [
            ...required
        ].filter((property)=>!(property in entity.properties));
        if (missing.length > 0) {
            issues.push({
                id: `required-properties-${entity.id}`,
                severity: "error",
                title: `${entity.name} thiếu property bắt buộc`,
                message: `Thiếu property kế thừa: ${missing.join(", ")}.`,
                path: `properties.csv → ${entity.id}`,
                entityId: entity.id,
                target: "entities"
            });
        }
    });
    const entityById = new Map(entities.map((entity)=>[
            entity.id,
            entity
        ]));
    relationships.forEach((relationship)=>{
        const definition = relationshipDefinitions.find((item)=>item.type === relationship.relationship);
        const fromEntity = entityById.get(relationship.fromEntityId);
        const toEntity = entityById.get(relationship.toEntityId);
        const matches = (actual, expected)=>!expected || expected.split("|").some((type)=>typeLineage(actual, nodeTypeDefinitions).has(type));
        if (definition && fromEntity && !matches(fromEntity.type, definition.from)) {
            issues.push({
                id: `from-type-${relationship.id}`,
                severity: "error",
                title: "Sai type đầu cạnh",
                message: `${fromEntity.type} không phù hợp với ${definition.from}.`,
                path: `relationships.csv.${relationship.id}`,
                entityId: fromEntity.id,
                target: "relationships"
            });
        }
        if (definition && toEntity && !matches(toEntity.type, definition.to)) {
            issues.push({
                id: `to-type-${relationship.id}`,
                severity: "error",
                title: "Sai type cuối cạnh",
                message: `${toEntity.type} không phù hợp với ${definition.to}.`,
                path: `relationships.csv.${relationship.id}`,
                entityId: toEntity.id,
                target: "relationships"
            });
        }
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
"[project]/app/components/KnowledgeGraphAIImports.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "KnowledgeGraphAIImports",
    ()=>KnowledgeGraphAIImports
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
const PAGE_SIZE = 25;
const DETAIL_PAGE_SIZE = 50;
const EMPTY_LAZY = {
    items: [],
    total: 0,
    hasMore: false,
    loading: false,
    error: ""
};
function KnowledgeGraphAIImports({ nodeTypes, nodeTypeProperties, relationshipTypes, onApplied }) {
    const [jobs, setJobs] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [jobsTotal, setJobsTotal] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    const [jobsHasMore, setJobsHasMore] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [statusFilter, setStatusFilter] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("all");
    const [searchTerm, setSearchTerm] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [selected, setSelected] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [activeTab, setActiveTab] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("nodes");
    const [selectedNodeId, setSelectedNodeId] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [selectedEdgeId, setSelectedEdgeId] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [showCreate, setShowCreate] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(true);
    const [sourceLabel, setSourceLabel] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [sourceUrl, setSourceUrl] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [content, setContent] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [loading, setLoading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(true);
    const [loadingMore, setLoadingMore] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [creating, setCreating] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [saving, setSaving] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [nodesByJob, setNodesByJob] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({});
    const [edgesByJob, setEdgesByJob] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({});
    async function reloadJobs(selectId) {
        setLoading(true);
        setError("");
        try {
            const result = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["listGraphImports"])({
                limit: PAGE_SIZE,
                offset: 0,
                status: statusFilter === "all" ? undefined : statusFilter,
                search: searchTerm.trim() || undefined
            });
            setJobs(result.items);
            setJobsTotal(result.total);
            setJobsHasMore(result.hasMore);
            const targetId = selectId ?? selected?.id ?? result.items[0]?.id;
            if (targetId) {
                const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["getGraphImportMeta"])(targetId);
                setSelected(meta);
            }
        } catch (caught) {
            setError(messageFor(caught, "Không tải được AI imports."));
        } finally{
            setLoading(false);
        }
    }
    async function loadMoreJobs() {
        if (!jobsHasMore || loadingMore) return;
        setLoadingMore(true);
        setError("");
        try {
            const result = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["listGraphImports"])({
                limit: PAGE_SIZE,
                offset: jobs.length,
                status: statusFilter === "all" ? undefined : statusFilter,
                search: searchTerm.trim() || undefined
            });
            setJobs((current)=>{
                const known = new Set(current.map((item)=>item.id));
                return [
                    ...current,
                    ...result.items.filter((item)=>!known.has(item.id))
                ];
            });
            setJobsHasMore(result.hasMore);
        } catch (caught) {
            setError(messageFor(caught, "Không tải thêm được AI imports."));
        } finally{
            setLoadingMore(false);
        }
    }
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        void reloadJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [
        statusFilter,
        searchTerm
    ]);
    const setNodesForJob = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])((jobId, updater)=>{
        setNodesByJob((current)=>({
                ...current,
                [jobId]: updater(current[jobId] ?? EMPTY_LAZY)
            }));
    }, []);
    const setEdgesForJob = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])((jobId, updater)=>{
        setEdgesByJob((current)=>({
                ...current,
                [jobId]: updater(current[jobId] ?? EMPTY_LAZY)
            }));
    }, []);
    async function loadNodes(jobId, reset = false) {
        const current = nodesByJob[jobId] ?? EMPTY_LAZY;
        setNodesForJob(jobId, (state)=>({
                ...state,
                loading: true,
                error: ""
            }));
        try {
            const offset = reset ? 0 : current.items.length;
            const result = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["listGraphImportNodes"])(jobId, {
                limit: DETAIL_PAGE_SIZE,
                offset
            });
            setNodesForJob(jobId, ()=>({
                    items: reset ? result.items : [
                        ...current.items,
                        ...result.items
                    ],
                    total: result.total,
                    hasMore: result.hasMore,
                    loading: false,
                    error: ""
                }));
        } catch (caught) {
            setNodesForJob(jobId, (state)=>({
                    ...state,
                    loading: false,
                    error: messageFor(caught, "Không tải được danh sách node.")
                }));
        }
    }
    async function loadEdges(jobId, reset = false) {
        const current = edgesByJob[jobId] ?? EMPTY_LAZY;
        setEdgesForJob(jobId, (state)=>({
                ...state,
                loading: true,
                error: ""
            }));
        try {
            const offset = reset ? 0 : current.items.length;
            const result = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["listGraphImportEdges"])(jobId, {
                limit: DETAIL_PAGE_SIZE,
                offset
            });
            setEdgesForJob(jobId, ()=>({
                    items: reset ? result.items : [
                        ...current.items,
                        ...result.items
                    ],
                    total: result.total,
                    hasMore: result.hasMore,
                    loading: false,
                    error: ""
                }));
        } catch (caught) {
            setEdgesForJob(jobId, (state)=>({
                    ...state,
                    loading: false,
                    error: messageFor(caught, "Không tải được danh sách edge.")
                }));
        }
    }
    function ensureNodesLoaded(jobId) {
        const state = nodesByJob[jobId];
        if (!state || !state.loading && state.items.length === 0 && state.total === 0 && !state.error) {
            void loadNodes(jobId, true);
        }
    }
    function ensureEdgesLoaded(jobId) {
        const state = edgesByJob[jobId];
        if (!state || !state.loading && state.items.length === 0 && state.total === 0 && !state.error) {
            void loadEdges(jobId, true);
        }
    }
    async function chooseJob(importId) {
        setError("");
        try {
            const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["getGraphImportMeta"])(importId);
            setSelected(meta);
            setSelectedNodeId("");
            setSelectedEdgeId("");
            setActiveTab("nodes");
            setShowCreate(false);
            ensureNodesLoaded(importId);
            ensureEdgesLoaded(importId);
        } catch (caught) {
            setError(messageFor(caught, "Không mở được AI import."));
        }
    }
    async function submitSource(event) {
        event.preventDefault();
        setError("");
        setCreating(true);
        try {
            const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["createGraphImport"])({
                sourceLabel: sourceLabel.trim(),
                ...sourceUrl.trim() ? {
                    sourceUrl: sourceUrl.trim()
                } : {},
                content: content.trim()
            });
            setSelected(meta);
            setJobs((current)=>{
                const summary = {
                    id: meta.id,
                    sourceLabel: meta.sourceLabel,
                    sourceUrl: meta.sourceUrl,
                    status: meta.status,
                    nodeCount: meta.nodeCount,
                    edgeCount: meta.edgeCount,
                    issueCount: meta.issueCount,
                    createdAt: meta.createdAt,
                    appliedAt: meta.appliedAt,
                    errorMessage: meta.errorMessage
                };
                return [
                    summary,
                    ...current.filter((item)=>item.id !== meta.id)
                ];
            });
            setShowCreate(false);
            setSourceLabel("");
            setSourceUrl("");
            setContent("");
            ensureNodesLoaded(meta.id);
            ensureEdgesLoaded(meta.id);
        } catch (caught) {
            setError(messageFor(caught, "Không tạo được graph proposal."));
        } finally{
            setCreating(false);
        }
    }
    function applyNodeMutation(jobId, mutation) {
        setSelected(mutation.meta);
        replaceSummary(mutation.summary);
        setNodesForJob(jobId, (state)=>({
                ...state,
                items: state.items.map((node)=>node.tempId === mutation.node.tempId ? mutation.node : node),
                total: mutation.meta.nodeCount
            }));
    }
    function applyEdgeMutation(jobId, mutation) {
        setSelected(mutation.meta);
        replaceSummary(mutation.summary);
        setEdgesForJob(jobId, (state)=>({
                ...state,
                items: state.items.map((edge)=>edge.tempId === mutation.edge.tempId ? mutation.edge : edge),
                total: mutation.meta.edgeCount
            }));
    }
    async function saveNode(node) {
        if (!selected) return;
        setSaving(true);
        setError("");
        try {
            const mutation = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["updateProposedGraphNode"])(selected.id, node.tempId, {
                entityId: node.entityId,
                type: node.type,
                canonicalName: node.canonicalName,
                aliases: node.aliases,
                properties: node.properties,
                selectedEntityId: node.selectedEntityId,
                decision: node.decision
            });
            applyNodeMutation(selected.id, mutation);
        } catch (caught) {
            setError(messageFor(caught, "Không lưu được node proposal."));
        } finally{
            setSaving(false);
        }
    }
    async function saveEdge(edge) {
        if (!selected) return;
        setSaving(true);
        setError("");
        try {
            const mutation = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["updateProposedGraphEdge"])(selected.id, edge.tempId, {
                fromRef: edge.fromRef,
                relationship: edge.relationship,
                toRef: edge.toRef,
                recommendations: edge.recommendations,
                source: edge.source,
                decision: edge.decision
            });
            applyEdgeMutation(selected.id, mutation);
        } catch (caught) {
            setError(messageFor(caught, "Không lưu được edge proposal."));
        } finally{
            setSaving(false);
        }
    }
    async function applyApproved() {
        if (!selected || !window.confirm("Apply toàn bộ node và edge đã duyệt vào knowledge graph hiện tại?")) return;
        setSaving(true);
        setError("");
        try {
            const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["applyGraphImport"])(selected.id);
            setSelected(meta);
            replaceSummary(meta);
            onApplied();
        } catch (caught) {
            setError(messageFor(caught, "Không apply được graph proposal."));
        } finally{
            setSaving(false);
        }
    }
    async function revalidateSelected() {
        if (!selected || !window.confirm("Chạy lại matching theo graph hiện tại? Mọi quyết định trong job sẽ trở về Chưa duyệt.")) return;
        setSaving(true);
        setError("");
        try {
            const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["revalidateGraphImport"])(selected.id);
            setSelected(meta);
            replaceSummary(meta);
            await loadNodes(selected.id, true);
            await loadEdges(selected.id, true);
        } catch (caught) {
            setError(messageFor(caught, "Không revalidate được graph proposal."));
        } finally{
            setSaving(false);
        }
    }
    async function removeNode(tempId) {
        if (!selected) return;
        if (!window.confirm("Xóa node proposal này? Các edge liên quan cũng sẽ bị xóa.")) return;
        setSaving(true);
        setError("");
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["deleteProposedGraphNode"])(selected.id, tempId);
            const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["getGraphImportMeta"])(selected.id);
            setSelected(meta);
            replaceSummary(meta);
            await loadNodes(selected.id, true);
            await loadEdges(selected.id, true);
            if (selectedNodeId === tempId) setSelectedNodeId("");
        } catch (caught) {
            setError(messageFor(caught, "Không xóa được node proposal."));
        } finally{
            setSaving(false);
        }
    }
    async function removeEdge(tempId) {
        if (!selected) return;
        if (!window.confirm("Xóa edge proposal này?")) return;
        setSaving(true);
        setError("");
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["deleteProposedGraphEdge"])(selected.id, tempId);
            const meta = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["getGraphImportMeta"])(selected.id);
            setSelected(meta);
            replaceSummary(meta);
            await loadEdges(selected.id, true);
            if (selectedEdgeId === tempId) setSelectedEdgeId("");
        } catch (caught) {
            setError(messageFor(caught, "Không xóa được edge proposal."));
        } finally{
            setSaving(false);
        }
    }
    async function removeSelectedJob() {
        if (!selected) return;
        if (!window.confirm(`Xóa import job "${selected.sourceLabel}"? Hành động này không thể hoàn tác.`)) return;
        setSaving(true);
        setError("");
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["deleteGraphImport"])(selected.id);
            setSelected(null);
            setSelectedNodeId("");
            setSelectedEdgeId("");
            setJobs((current)=>current.filter((item)=>item.id !== selected.id));
            setNodesByJob((current)=>{
                const { [selected.id]: _removed, ...rest } = current;
                return rest;
            });
            setEdgesByJob((current)=>{
                const { [selected.id]: _removed, ...rest } = current;
                return rest;
            });
        } catch (caught) {
            setError(messageFor(caught, "Không xóa được import job."));
        } finally{
            setSaving(false);
        }
    }
    function replaceSummary(meta) {
        setJobs((current)=>current.map((item)=>item.id === meta.id ? meta : item));
    }
    const currentNodes = selected ? nodesByJob[selected.id]?.items ?? [] : [];
    const currentEdges = selected ? edgesByJob[selected.id]?.items ?? [] : [];
    const nodesState = selected ? nodesByJob[selected.id] ?? EMPTY_LAZY : EMPTY_LAZY;
    const edgesState = selected ? edgesByJob[selected.id] ?? EMPTY_LAZY : EMPTY_LAZY;
    const selectedNode = currentNodes.find((item)=>item.tempId === selectedNodeId) ?? null;
    const selectedEdge = currentEdges.find((item)=>item.tempId === selectedEdgeId) ?? null;
    const approvedCount = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        const approved = [
            ...currentNodes,
            ...currentEdges
        ].filter((item)=>item.decision.startsWith("approve_")).length;
        return approved > 0 ? approved : 0;
    }, [
        currentNodes,
        currentEdges
    ]);
    function handleTabChange(tab) {
        setActiveTab(tab);
        if (!selected) return;
        if (tab === "nodes") ensureNodesLoaded(selected.id);
        if (tab === "edges") ensureEdgesLoaded(selected.id);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "kgAiWorkspace",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "kgAiHeader",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Human-in-the-loop extraction"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 448,
                                columnNumber: 14
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "AI Imports"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 448,
                                columnNumber: 69
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Gemini tạo proposal; rule matcher tìm bản ghi hiện có; admin là người quyết định cuối."
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 448,
                                columnNumber: 88
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 448,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "kgPrimaryButton",
                        type: "button",
                        onClick: ()=>setShowCreate((value)=>!value),
                        children: "＋ Nguồn mới"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 449,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 447,
                columnNumber: 7
            }, this),
            error && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "pageError kgAiError",
                children: error
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 452,
                columnNumber: 17
            }, this),
            showCreate && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                className: "kgAiSourceForm",
                onSubmit: submitSource,
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiFormTitle",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "✦"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 456,
                                columnNumber: 42
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Tạo graph proposal"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 456,
                                        columnNumber: 61
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: "Nguồn được coi là dữ liệu không tin cậy và không được quyền thay đổi schema."
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 456,
                                        columnNumber: 86
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 456,
                                columnNumber: 56
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 456,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiFormGrid",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Nhãn nguồn"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 458,
                                        columnNumber: 20
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        required: true,
                                        minLength: 2,
                                        value: sourceLabel,
                                        onChange: (event)=>setSourceLabel(event.target.value),
                                        placeholder: "Bài viết ẩm thực Hà Nội"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 458,
                                        columnNumber: 43
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 458,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "URL provenance (không bắt buộc)"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 459,
                                        columnNumber: 20
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: sourceUrl,
                                        onChange: (event)=>setSourceUrl(event.target.value),
                                        placeholder: "https://..."
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 459,
                                        columnNumber: 64
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 459,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 457,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Nội dung nguồn"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 461,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                                required: true,
                                minLength: 20,
                                maxLength: 50000,
                                value: content,
                                onChange: (event)=>setContent(event.target.value),
                                placeholder: "Dán nội dung để AI trích xuất node và edge…",
                                rows: 9
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 461,
                                columnNumber: 45
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 461,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("footer", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    content.length.toLocaleString("vi-VN"),
                                    " / 50.000 ký tự"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 462,
                                columnNumber: 19
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                disabled: creating,
                                type: "submit",
                                children: creating ? "Gemini đang trích xuất…" : "✦ Tạo proposal"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 462,
                                columnNumber: 89
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 462,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 455,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiLayout",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                        className: "kgAiJobList",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: [
                                            "Hiển thị ",
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                children: jobs.length.toLocaleString("vi-VN")
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 470,
                                                columnNumber: 24
                                            }, this),
                                            " / ",
                                            jobsTotal.toLocaleString("vi-VN"),
                                            " import jobs"
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 469,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        type: "button",
                                        onClick: ()=>void reloadJobs(),
                                        children: "↻"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 472,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 468,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgAiJobFilters",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        type: "search",
                                        value: searchTerm,
                                        onChange: (event)=>setSearchTerm(event.target.value),
                                        placeholder: "Tìm theo nhãn hoặc ID…"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 475,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                        value: statusFilter,
                                        onChange: (event)=>setStatusFilter(event.target.value),
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "all",
                                                children: "Tất cả trạng thái"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 482,
                                                columnNumber: 15
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "needs_review",
                                                children: "Needs review"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 483,
                                                columnNumber: 15
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "applied",
                                                children: "Applied"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 484,
                                                columnNumber: 15
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "failed",
                                                children: "Failed"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 485,
                                                columnNumber: 15
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "extracting",
                                                children: "Extracting"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 486,
                                                columnNumber: 15
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 481,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 474,
                                columnNumber: 11
                            }, this),
                            loading && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgAiMuted",
                                children: "Đang tải imports…"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 489,
                                columnNumber: 23
                            }, this),
                            !loading && jobs.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgAiMuted",
                                children: "Chưa có AI import."
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 490,
                                columnNumber: 45
                            }, this),
                            jobs.map((job)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    type: "button",
                                    className: selected?.id === job.id ? "active" : "",
                                    onClick: ()=>void chooseJob(job.id),
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: `status status-${job.status === "applied" ? "completed" : job.status === "failed" ? "failed" : "warning"}`,
                                                    children: job.status.replaceAll("_", " ")
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 491,
                                                    columnNumber: 161
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("time", {
                                                    children: new Date(job.createdAt).toLocaleDateString("vi-VN")
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 491,
                                                    columnNumber: 326
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 491,
                                            columnNumber: 156
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                            children: job.sourceLabel
                                        }, void 0, false, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 491,
                                            columnNumber: 398
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            children: [
                                                job.nodeCount,
                                                " nodes · ",
                                                job.edgeCount,
                                                " edges · ",
                                                job.issueCount,
                                                " issues"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 491,
                                            columnNumber: 422
                                        }, this)
                                    ]
                                }, job.id, true, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 491,
                                    columnNumber: 30
                                }, this)),
                            jobsHasMore && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                type: "button",
                                className: "kgSecondaryButton kgAiLoadMore",
                                disabled: loadingMore,
                                onClick: ()=>void loadMoreJobs(),
                                children: loadingMore ? "Đang tải…" : `Tải thêm ${Math.min(PAGE_SIZE, jobsTotal - jobs.length)} jobs`
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 493,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 467,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        className: "kgAiReview",
                        children: !selected ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "detailEmpty",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                    children: "Chọn một import để review"
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 500,
                                    columnNumber: 53
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    children: "Node, edge và matching result sẽ xuất hiện tại đây."
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 500,
                                    columnNumber: 85
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 500,
                            columnNumber: 24
                        }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                    className: "kgAiReviewHeader",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "eyebrow",
                                                    children: [
                                                        "Proposal ",
                                                        selected.id.slice(0, 8)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 501,
                                                    columnNumber: 55
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                                    children: selected.sourceLabel
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 501,
                                                    columnNumber: 116
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    children: [
                                                        "Schema ",
                                                        selected.schemaVersion,
                                                        " · Ontology ",
                                                        selected.ontologyVersion
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 501,
                                                    columnNumber: 147
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 501,
                                            columnNumber: 50
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: `status status-${selected.status === "applied" ? "completed" : selected.status === "failed" ? "failed" : "warning"}`,
                                                    children: selected.status.replaceAll("_", " ")
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 501,
                                                    columnNumber: 234
                                                }, this),
                                                selected.status === "needs_review" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            className: "kgSecondaryButton",
                                                            disabled: saving,
                                                            type: "button",
                                                            onClick: ()=>void revalidateSelected(),
                                                            children: "↻ Revalidate"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                            lineNumber: 501,
                                                            columnNumber: 455
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            className: "kgPrimaryButton",
                                                            disabled: saving || approvedCount === 0,
                                                            type: "button",
                                                            onClick: ()=>void applyApproved(),
                                                            children: [
                                                                "Apply ",
                                                                approvedCount,
                                                                " đã duyệt"
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                            lineNumber: 501,
                                                            columnNumber: 588
                                                        }, this)
                                                    ]
                                                }, void 0, true),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    className: "kgDangerButton",
                                                    disabled: saving,
                                                    type: "button",
                                                    onClick: ()=>void removeSelectedJob(),
                                                    children: "🗑 Xóa job"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 501,
                                                    columnNumber: 759
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 501,
                                            columnNumber: 229
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 501,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("nav", {
                                    className: "kgAiTabs",
                                    children: [
                                        "nodes",
                                        "edges",
                                        "source"
                                    ].map((tab)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            type: "button",
                                            className: activeTab === tab ? "active" : "",
                                            onClick: ()=>handleTabChange(tab),
                                            children: tab === "nodes" ? `Nodes (${nodesState.total || selected.nodeCount})` : tab === "edges" ? `Edges (${edgesState.total || selected.edgeCount})` : "Nguồn & warnings"
                                        }, tab, false, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 502,
                                            columnNumber: 99
                                        }, this))
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 502,
                                    columnNumber: 13
                                }, this),
                                activeTab === "nodes" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "kgAiReviewSplit",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgAiProposalList",
                                            children: [
                                                nodesState.error ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "kgAiMuted",
                                                    children: nodesState.error
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 504,
                                                    columnNumber: 126
                                                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(ProposalNodeTable, {
                                                    nodes: currentNodes,
                                                    selectedId: selectedNodeId,
                                                    onSelect: setSelectedNodeId
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 504,
                                                    columnNumber: 176
                                                }, this),
                                                nodesState.hasMore && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    type: "button",
                                                    className: "kgSecondaryButton kgAiLoadMore",
                                                    disabled: nodesState.loading,
                                                    onClick: ()=>void loadNodes(selected.id, false),
                                                    children: nodesState.loading ? "Đang tải…" : `Tải thêm ${Math.min(DETAIL_PAGE_SIZE, nodesState.total - currentNodes.length)} nodes`
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 504,
                                                    columnNumber: 299
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 504,
                                            columnNumber: 72
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgAiProposalInspector",
                                            children: selectedNode ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(NodeEditor, {
                                                node: selectedNode,
                                                nodeTypes: nodeTypes,
                                                nodeTypeProperties: nodeTypeProperties,
                                                saving: saving,
                                                onSave: saveNode,
                                                onDelete: removeNode
                                            }, `${selectedNode.tempId}-${selectedNode.decision}-${selectedNode.canonicalName}`, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 504,
                                                columnNumber: 639
                                            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(InspectorEmpty, {
                                                label: "Chọn node để xem matching và chỉnh sửa"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 504,
                                                columnNumber: 880
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 504,
                                            columnNumber: 584
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 504,
                                    columnNumber: 39
                                }, this),
                                activeTab === "edges" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "kgAiReviewSplit",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgAiProposalList",
                                            children: [
                                                edgesState.error ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "kgAiMuted",
                                                    children: edgesState.error
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 505,
                                                    columnNumber: 126
                                                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(ProposalEdgeTable, {
                                                    edges: currentEdges,
                                                    nodes: currentNodes,
                                                    selectedId: selectedEdgeId,
                                                    onSelect: setSelectedEdgeId
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 505,
                                                    columnNumber: 176
                                                }, this),
                                                edgesState.hasMore && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    type: "button",
                                                    className: "kgSecondaryButton kgAiLoadMore",
                                                    disabled: edgesState.loading,
                                                    onClick: ()=>void loadEdges(selected.id, false),
                                                    children: edgesState.loading ? "Đang tải…" : `Tải thêm ${Math.min(DETAIL_PAGE_SIZE, edgesState.total - currentEdges.length)} edges`
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 505,
                                                    columnNumber: 320
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 505,
                                            columnNumber: 72
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgAiProposalInspector",
                                            children: selectedEdge ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(EdgeEditor, {
                                                edge: selectedEdge,
                                                nodes: currentNodes,
                                                relationshipTypes: relationshipTypes,
                                                saving: saving,
                                                onSave: saveEdge,
                                                onDelete: removeEdge
                                            }, `${selectedEdge.tempId}-${selectedEdge.decision}-${selectedEdge.relationship}`, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 505,
                                                columnNumber: 660
                                            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(InspectorEmpty, {
                                                label: "Chọn edge để xem và chỉnh sửa"
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 505,
                                                columnNumber: 897
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 505,
                                            columnNumber: 605
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 505,
                                    columnNumber: 39
                                }, this),
                                activeTab === "source" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "kgAiSourceReview",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                                    children: "Nguồn"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 506,
                                                    columnNumber: 79
                                                }, this),
                                                selected.sourceUrl && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                                                    href: selected.sourceUrl,
                                                    target: "_blank",
                                                    rel: "noreferrer",
                                                    children: selected.sourceUrl
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 506,
                                                    columnNumber: 116
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("pre", {
                                                    children: selected.sourceContent
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 506,
                                                    columnNumber: 203
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 506,
                                            columnNumber: 74
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                                    children: "Warnings"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 506,
                                                    columnNumber: 249
                                                }, this),
                                                selected.warnings.length ? selected.warnings.map((warning)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                        children: [
                                                            "△ ",
                                                            warning
                                                        ]
                                                    }, warning, true, {
                                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                        lineNumber: 506,
                                                        columnNumber: 329
                                                    }, this)) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "kgAiMuted",
                                                    children: "Không có warning từ extractor."
                                                }, void 0, false, {
                                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                    lineNumber: 506,
                                                    columnNumber: 365
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                            lineNumber: 506,
                                            columnNumber: 244
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 506,
                                    columnNumber: 40
                                }, this)
                            ]
                        }, void 0, true)
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 499,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 466,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 446,
        columnNumber: 5
    }, this);
}
function ProposalNodeTable({ nodes, selectedId, onSelect }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
        className: "kgAiCompactTable",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            children: "Node"
                        }, void 0, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 515,
                            columnNumber: 57
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            children: "Match"
                        }, void 0, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 515,
                            columnNumber: 70
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            children: "Decision"
                        }, void 0, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 515,
                            columnNumber: 84
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                    lineNumber: 515,
                    columnNumber: 53
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 515,
                columnNumber: 46
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                children: nodes.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                        className: selectedId === node.tempId ? "active" : "",
                        onClick: ()=>onSelect(node.tempId),
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: node.canonicalName
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 515,
                                        columnNumber: 261
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: [
                                            node.type,
                                            " · ",
                                            node.entityId
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 515,
                                        columnNumber: 288
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 515,
                                columnNumber: 257
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(MatchBadge, {
                                    status: node.matchStatus
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 515,
                                    columnNumber: 341
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 515,
                                columnNumber: 337
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(DecisionBadge, {
                                    decision: node.decision
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 515,
                                    columnNumber: 390
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 515,
                                columnNumber: 386
                            }, this)
                        ]
                    }, node.tempId, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 515,
                        columnNumber: 142
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 515,
                columnNumber: 114
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 515,
        columnNumber: 10
    }, this);
}
function ProposalEdgeTable({ edges, nodes, selectedId, onSelect }) {
    const name = (ref)=>nodes.find((node)=>node.tempId === ref)?.canonicalName ?? ref;
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
        className: "kgAiCompactTable",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            children: "Edge"
                        }, void 0, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 520,
                            columnNumber: 57
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            children: "Match"
                        }, void 0, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 520,
                            columnNumber: 70
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            children: "Decision"
                        }, void 0, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 520,
                            columnNumber: 84
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                    lineNumber: 520,
                    columnNumber: 53
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 520,
                columnNumber: 46
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                children: edges.map((edge)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                        className: selectedId === edge.tempId ? "active" : "",
                        onClick: ()=>onSelect(edge.tempId),
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: [
                                            name(edge.fromRef),
                                            " → ",
                                            name(edge.toRef)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 520,
                                        columnNumber: 261
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: edge.relationship
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 520,
                                        columnNumber: 309
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 520,
                                columnNumber: 257
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(MatchBadge, {
                                    status: edge.matchStatus
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 520,
                                    columnNumber: 352
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 520,
                                columnNumber: 348
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(DecisionBadge, {
                                    decision: edge.decision
                                }, void 0, false, {
                                    fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                    lineNumber: 520,
                                    columnNumber: 401
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 520,
                                columnNumber: 397
                            }, this)
                        ]
                    }, edge.tempId, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 520,
                        columnNumber: 142
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 520,
                columnNumber: 114
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 520,
        columnNumber: 10
    }, this);
}
function NodeEditor({ node, nodeTypes, nodeTypeProperties, saving, onSave, onDelete }) {
    const [draft, setDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(node);
    const [aliases, setAliases] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(node.aliases.join("\n"));
    const [properties, setProperties] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(JSON.stringify(node.properties, null, 2));
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const parsedProperties = parseProperties(properties);
    const schemaProperties = nodeTypeProperties[draft.type];
    const requiredProperties = uniqueProperties(schemaProperties?.requiredProperties ?? [], node.requiredProperties ?? []);
    const optionalProperties = uniqueProperties(schemaProperties?.optionalProperties ?? [], node.optionalProperties ?? []).filter((key)=>!requiredProperties.includes(key));
    const displayedProperties = parsedProperties ?? node.properties;
    const missingRequiredCount = requiredProperties.filter((key)=>!String(displayedProperties[key] ?? "").trim()).length;
    async function submit(event) {
        event.preventDefault();
        if (!parsedProperties) {
            setError("Properties JSON không hợp lệ.");
            return;
        }
        const missing = requiredProperties.filter((key)=>!String(parsedProperties[key] ?? "").trim());
        if (missing.length > 0) {
            setError(`Thiếu trường bắt buộc: ${missing.join(", ")}`);
            return;
        }
        setError("");
        await onSave({
            ...draft,
            aliases: aliases.split("\n").map((item)=>item.trim()).filter(Boolean),
            properties: parsedProperties
        });
    }
    function updateProperty(key, value) {
        const next = {
            ...parsedProperties ?? node.properties,
            [key]: value
        };
        setProperties(JSON.stringify(next, null, 2));
    }
    function ruleLabel(rule) {
        if (rule === "name_exact") return "Name trùng khớp";
        if (rule === "alias_exact") return "Alias trùng khớp";
        if (rule.startsWith("name_similarity:")) return `Name tương tự ${(parseFloat(rule.split(":")[1]) * 100).toFixed(0)}%`;
        return rule;
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
        className: "kgAiInspectorForm",
        onSubmit: submit,
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Proposed node"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 77
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                children: draft.canonicalName
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 117
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 72
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiInspectorHeaderRight",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(MatchBadge, {
                                status: node.matchStatus
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 195
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "kgAiConfidence",
                                children: [
                                    Math.round(node.confidence * 100),
                                    "%"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 235
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 153
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 64
            }, this),
            node.validationIssues.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiIssues",
                children: node.validationIssues.map((issue)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: [
                            "! ",
                            issue
                        ]
                    }, issue, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 429
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 363
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiInspectorGrid",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    "Entity ID ",
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
                                        className: "kgAiRequired",
                                        children: "*"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 573,
                                        columnNumber: 524
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 508
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                required: true,
                                value: draft.entityId,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            entityId: event.target.value
                                        }))
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 564
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 501
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    "Canonical name ",
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
                                        className: "kgAiRequired",
                                        children: "*"
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 573,
                                        columnNumber: 733
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 712
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                required: true,
                                value: draft.canonicalName,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            canonicalName: event.target.value
                                        }))
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 773
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 705
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 466
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: [
                            "Node type ",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
                                className: "kgAiRequired",
                                children: "*"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 953
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 937
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                        required: true,
                        value: draft.type,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    type: event.target.value
                                })),
                        children: nodeTypes.map((type)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                children: type
                            }, type, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 1142
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 993
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 930
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Aliases · mỗi dòng một alias"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 1202
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                        rows: 3,
                        value: aliases,
                        onChange: (event)=>setAliases(event.target.value)
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 1243
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 1195
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiPropertySection",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h5", {
                        children: [
                            "Trường bắt buộc ",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "kgAiRequired",
                                children: "*"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 1398
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: missingRequiredCount ? "kgAiFieldMissingCount" : "kgAiFieldComplete",
                                children: missingRequiredCount ? `${missingRequiredCount} thiếu` : "Đã đủ"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 1437
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 1378
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiPropertyGrid",
                        children: requiredProperties.map((key)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(PropertyField, {
                                name: key,
                                value: String(displayedProperties[key] ?? ""),
                                required: true,
                                onChange: updateProperty
                            }, key, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 1669
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 1602
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 1341
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiPropertySection",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h5", {
                        children: [
                            "Trường tùy chọn ",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "kgAiOptional",
                                children: "Nên nhập"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 1860
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 1840
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiPropertyGrid",
                        children: optionalProperties.map((key)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(PropertyField, {
                                name: key,
                                value: String(displayedProperties[key] ?? ""),
                                onChange: updateProperty
                            }, key, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 1978
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 1911
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 1803
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Properties JSON"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 2110
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                        className: "mono",
                        rows: 5,
                        value: properties,
                        onChange: (event)=>setProperties(event.target.value)
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 2138
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 2103
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiEvidence",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                        children: "Evidence"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 2289
                    }, this),
                    node.evidence.map((value)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("blockquote", {
                            children: value
                        }, value, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 573,
                            columnNumber: 2334
                        }, this))
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 2259
            }, this),
            node.matchCandidates.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiMatchCandidates",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h5", {
                        children: "Entity hiện có"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 2459
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiCandidateList",
                        children: node.matchCandidates.map((candidate)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: `kgAiCandidate ${draft.selectedEntityId === candidate.entityId ? "selected" : ""}`,
                                onClick: ()=>setDraft((current)=>({
                                            ...current,
                                            selectedEntityId: candidate.entityId
                                        })),
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgAiCandidateHeader",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                children: candidate.canonicalName
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 573,
                                                columnNumber: 2814
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgAiScore",
                                                children: candidate.score
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 573,
                                                columnNumber: 2846
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 573,
                                        columnNumber: 2777
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgAiCandidateMeta",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: candidate.entityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 573,
                                                columnNumber: 2939
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: candidate.type
                                            }, void 0, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 573,
                                                columnNumber: 2972
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 573,
                                        columnNumber: 2904
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgAiCandidateRules",
                                        children: candidate.matchedRules.map((rule)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgAiRuleTag",
                                                children: ruleLabel(rule)
                                            }, rule, false, {
                                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                                lineNumber: 573,
                                                columnNumber: 3081
                                            }, this))
                                    }, void 0, false, {
                                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                        lineNumber: 573,
                                        columnNumber: 3007
                                    }, this)
                                ]
                            }, candidate.entityId, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 2558
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 2482
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 2422
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Quyết định"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 3182
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                        value: draft.decision,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    decision: event.target.value
                                })),
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "pending",
                                children: "Chưa quyết định"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 3361
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "approve_create",
                                children: "Duyệt tạo mới"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 3409
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "approve_existing",
                                children: "Dùng entity hiện có"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 3462
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "reject",
                                children: "Từ chối"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 573,
                                columnNumber: 3523
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 3205
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 3175
            }, this),
            error && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                className: "kgAiFormError",
                children: error
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 3589
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("footer", {
                className: "kgAiInspectorFooter",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "kgDangerButton",
                        type: "button",
                        disabled: saving,
                        onClick: ()=>void onDelete(node.tempId),
                        children: "🗑 Xóa node"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 3670
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "kgPrimaryButton",
                        disabled: saving,
                        type: "submit",
                        children: saving ? "Đang lưu…" : "Lưu & chạy lại matching"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 573,
                        columnNumber: 3800
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 573,
                columnNumber: 3630
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 573,
        columnNumber: 10
    }, this);
}
function PropertyField({ name, value, required = false, onChange }) {
    const missing = required && !value.trim();
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
        className: missing ? "kgAiPropertyMissing" : "",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                children: [
                    name,
                    missing && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("em", {
                        children: "Thiếu"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 578,
                        columnNumber: 90
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 578,
                columnNumber: 66
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                required: required,
                "aria-invalid": missing,
                value: value,
                onChange: (event)=>onChange(name, event.target.value),
                placeholder: `Nhập ${name}…`
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 578,
                columnNumber: 112
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 578,
        columnNumber: 10
    }, this);
}
function parseProperties(value) {
    try {
        const parsed = JSON.parse(value);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
        return parsed;
    } catch  {
        return null;
    }
}
function uniqueProperties(...groups) {
    return [
        ...new Set(groups.flat())
    ].sort();
}
function EdgeEditor({ edge, nodes, relationshipTypes, saving, onSave, onDelete }) {
    const [draft, setDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(edge);
    const [recommendations, setRecommendations] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(JSON.stringify(edge.recommendations, null, 2));
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
        className: "kgAiInspectorForm",
        onSubmit: (event)=>{
            event.preventDefault();
            try {
                const parsed = JSON.parse(recommendations);
                if (!Array.isArray(parsed)) throw new Error();
                setError("");
                void onSave({
                    ...draft,
                    recommendations: parsed
                });
            } catch  {
                setError("Recommendations phải là JSON array hợp lệ.");
            }
        },
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "eyebrow",
                                children: "Proposed edge"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 340
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                children: draft.relationship
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 380
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 335
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgAiInspectorHeaderRight",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(MatchBadge, {
                                status: edge.matchStatus
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 457
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "kgAiConfidence",
                                children: [
                                    Math.round(edge.confidence * 100),
                                    "%"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 497
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 415
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 327
            }, this),
            edge.validationIssues.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiIssues",
                children: edge.validationIssues.map((issue)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: [
                            "! ",
                            issue
                        ]
                    }, issue, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 691
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 625
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "From node"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 735
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                        value: draft.fromRef,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    fromRef: event.target.value
                                })),
                        children: nodes.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: node.tempId,
                                children: [
                                    node.canonicalName,
                                    " · ",
                                    node.type
                                ]
                            }, node.tempId, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 899
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 757
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 728
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Relationship"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1014
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                        value: draft.relationship,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    relationship: event.target.value
                                })),
                        children: relationshipTypes.map((type)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                children: type
                            }, type, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 1203
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1039
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 1007
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "To node"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1263
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                        value: draft.toRef,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    toRef: event.target.value
                                })),
                        children: nodes.map((node)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: node.tempId,
                                children: [
                                    node.canonicalName,
                                    " · ",
                                    node.type
                                ]
                            }, node.tempId, true, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 1421
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1283
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 1256
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Recommendations JSON"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1536
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                        className: "mono",
                        rows: 6,
                        value: recommendations,
                        onChange: (event)=>setRecommendations(event.target.value)
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1569
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 1529
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Nguồn"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1707
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                        value: draft.source,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    source: event.target.value
                                }))
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1725
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 1700
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgAiEvidence",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                        children: "Evidence"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1883
                    }, this),
                    edge.evidence.map((value)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("blockquote", {
                            children: value
                        }, value, false, {
                            fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                            lineNumber: 599,
                            columnNumber: 1928
                        }, this))
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 1853
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "Quyết định"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 1987
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                        value: draft.decision,
                        onChange: (event)=>setDraft((current)=>({
                                    ...current,
                                    decision: event.target.value
                                })),
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "pending",
                                children: "Chưa quyết định"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 2166
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "approve_create",
                                children: "Duyệt tạo edge"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 2214
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "approve_existing",
                                children: "Edge đã tồn tại · thêm nguồn"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 2268
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                value: "reject",
                                children: "Từ chối"
                            }, void 0, false, {
                                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                                lineNumber: 599,
                                columnNumber: 2338
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 2010
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 1980
            }, this),
            error && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                className: "kgAiFormError",
                children: error
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 2404
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("footer", {
                className: "kgAiInspectorFooter",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "kgDangerButton",
                        type: "button",
                        disabled: saving,
                        onClick: ()=>void onDelete(edge.tempId),
                        children: "🗑 Xóa edge"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 2485
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "kgPrimaryButton",
                        disabled: saving,
                        type: "submit",
                        children: saving ? "Đang lưu…" : "Lưu & validate lại"
                    }, void 0, false, {
                        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                        lineNumber: 599,
                        columnNumber: 2615
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 599,
                columnNumber: 2445
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 599,
        columnNumber: 10
    }, this);
}
function MatchBadge({ status }) {
    const tone = status === "existing" ? "completed" : status === "new" ? "running" : "warning";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: `status status-${tone}`,
        children: status.replaceAll("_", " ")
    }, void 0, false, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 602,
        columnNumber: 155
    }, this);
}
function DecisionBadge({ decision }) {
    const tone = decision.startsWith("approve_") ? "completed" : decision === "reject" ? "failed" : "draft";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: `status status-${tone}`,
        children: decision.replaceAll("_", " ")
    }, void 0, false, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 603,
        columnNumber: 174
    }, this);
}
function InspectorEmpty({ label }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "kgAiInspectorEmpty",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                children: "◇"
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 604,
                columnNumber: 100
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                children: label
            }, void 0, false, {
                fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
                lineNumber: 604,
                columnNumber: 114
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/components/KnowledgeGraphAIImports.tsx",
        lineNumber: 604,
        columnNumber: 64
    }, this);
}
function messageFor(caught, fallback) {
    return caught instanceof __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["APIError"] || caught instanceof Error ? caught.message : fallback;
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
var __TURBOPACK__imported__module__$5b$project$5d2f$app$2f$components$2f$KnowledgeGraphAIImports$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/app/components/KnowledgeGraphAIImports.tsx [app-ssr] (ecmascript)");
"use client";
;
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
        id: "aiImports",
        label: "✦ AI Imports"
    },
    {
        id: "validation",
        label: "Validation"
    }
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
    const [propertyRows, setPropertyRows] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])((0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseProperties"])(__TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["rawDataset"]["properties.csv"]));
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
        type: "TravelPlace",
        status: "draft"
    });
    const importInputRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const nodeTypeDefinitions = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>(0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseNodeTypeDefinitions"])(datasetFiles["schema.yaml"]), [
        datasetFiles
    ]);
    const nodeTypeProperties = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>Object.fromEntries(nodeDefinitions.map((node)=>[
                node.type,
                (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["resolveNodeTypeProperties"])(node.type, nodeTypeDefinitions)
            ])), [
        nodeDefinitions,
        nodeTypeDefinitions
    ]);
    const issues = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>(0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["validateKnowledgeGraph"])(entities, relationshipRows, nodeDefinitions, relationshipDefinitions, nodeTypeDefinitions), [
        entities,
        nodeDefinitions,
        nodeTypeDefinitions,
        relationshipDefinitions,
        relationshipRows
    ]);
    const errorCount = issues.filter((issue)=>issue.severity === "error").length;
    const typeFilterOptions = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>[
            "all",
            ...nodeDefinitions.map((node)=>node.type)
        ], [
        nodeDefinitions
    ]);
    const persistedCount = entities.filter((entity)=>entity.status !== "missing").length;
    const selectedEntity = entities.find((entity)=>entity.id === selectedId) ?? null;
    const selectedProperties = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>propertyRows.filter((property)=>property.entityId === selectedId), [
        propertyRows,
        selectedId
    ]);
    const selectedRelationships = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>relationshipRows.filter((relationship)=>relationship.fromEntityId === selectedId || relationship.toEntityId === selectedId), [
        relationshipRows,
        selectedId
    ]);
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
            const loadedProperties = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseProperties"])(files["properties.csv"]);
            const loadedRelationships = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseRelationships"])(files["relationships.csv"]);
            const loadedOntology = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["parseOntology"])(files["ontology.yaml"]);
            const mergedNodes = loadedOntology.nodes.length > 0 ? loadedOntology.nodes : __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ontologyNodes"];
            const mergedRelationships = loadedOntology.relationships.length > 0 ? loadedOntology.relationships : __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ontologyRelationships"];
            const referenced = Array.from(new Set([
                ...loadedAliases.map((item)=>item.entityId),
                ...loadedRelationships.flatMap((item)=>[
                        item.fromEntityId,
                        item.toEntityId
                    ])
            ]));
            setAliasRows(loadedAliases);
            setPropertyRows(loadedProperties);
            setRelationshipRows(loadedRelationships);
            setNodeDefinitions(mergedNodes);
            setRelationshipDefinitions(mergedRelationships);
            setDatasetFiles(files);
            const combinedEntities = loadedEntities.map((entity)=>({
                    ...entity,
                    aliases: loadedAliases.filter((item)=>item.entityId === entity.id).map((item)=>item.alias),
                    properties: Object.fromEntries(loadedProperties.filter((item)=>item.entityId === entity.id).map((item)=>[
                            item.key,
                            item.value
                        ]))
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
                    properties: Object.fromEntries(loadedProperties.filter((item)=>item.entityId === entityId).map((item)=>[
                            item.key,
                            item.value
                        ])),
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
    async function saveProperties(nextRows) {
        const content = (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeProperties"])(nextRows);
        await persistFile("properties.csv", content, "Đã lưu properties trực tiếp vào properties.csv.");
        setPropertyRows(nextRows);
        setEntities((current)=>current.map((entity)=>({
                    ...entity,
                    properties: Object.fromEntries(nextRows.filter((property)=>property.entityId === entity.id).map((property)=>[
                            property.key,
                            property.value
                        ]))
                })));
    }
    async function saveEntityIdentity(entityId, input) {
        const nextEntities = entities.map((entity)=>entity.id === entityId ? {
                ...entity,
                ...input
            } : entity);
        await persistFile("entities.csv", (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$knowledge$2d$graph$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["serializeEntities"])(nextEntities), "Đã lưu thông tin entity trực tiếp vào entities.csv.");
        setEntities(nextEntities);
    }
    function beginAddEntity(prefill) {
        setEntityEditor(prefill?.id ?? "new");
        setEntityDraft({
            id: prefill?.id ?? "",
            name: prefill?.name ?? "",
            type: prefill?.type ?? nodeDefinitions[0]?.type ?? "TravelPlace",
            status: prefill?.status === "verified" ? "verified" : "draft"
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
                                lineNumber: 476,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                children: "Knowledge Graph"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 477,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgLead",
                                children: "Kiểm tra entity, alias và ontology trước khi dữ liệu được đưa vào Planner."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 478,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 475,
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
                                lineNumber: 483,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgSecondaryButton",
                                type: "button",
                                onClick: ()=>importInputRef.current?.click(),
                                children: "⇧ Import dataset"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 491,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: runValidation,
                                children: "✓ Validate graph"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 494,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 482,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 474,
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
                                lineNumber: 502,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Local prototype snapshot"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 504,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                        children: datasetLoading ? "Đang đọc dataset…" : "knowledge-graph-real-v2 · 6 files"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 505,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 503,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 501,
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
                                lineNumber: 509,
                                columnNumber: 40
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Draft workspace"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 510,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                type: "button",
                                onClick: resetDraft,
                                children: "Tải lại từ file"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 511,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 508,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 500,
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
                        lineNumber: 517,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: notice
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 518,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        "aria-label": "Đóng thông báo",
                        onClick: ()=>setNotice(""),
                        children: "×"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 519,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 516,
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
                                lineNumber: 525,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: persistedCount
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 526,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    entities.filter((entity)=>entity.status === "missing").length,
                                    " tham chiếu chưa tồn tại"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 527,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 524,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Aliases"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 530,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: aliasRows.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 531,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: "Tiếng Việt và tiếng Anh"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 532,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 529,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Relationships"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 535,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: relationshipRows.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 536,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    relationshipDefinitions.length,
                                    " loại đã khai báo"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 537,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 534,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                        className: errorCount ? "kgMetricDanger" : "",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Validation issues"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 540,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                children: issues.length
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 541,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                children: [
                                    errorCount,
                                    " lỗi đang chặn publish"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 542,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 539,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 523,
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
                                lineNumber: 555,
                                columnNumber: 41
                            }, this)
                        ]
                    }, tab.id, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 548,
                        columnNumber: 11
                    }, this))
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 546,
                columnNumber: 7
            }, this),
            activeTab === "aiImports" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$app$2f$components$2f$KnowledgeGraphAIImports$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["KnowledgeGraphAIImports"], {
                nodeTypes: nodeDefinitions.map((node)=>node.type),
                nodeTypeProperties: nodeTypeProperties,
                relationshipTypes: relationshipDefinitions.map((relationship)=>relationship.type),
                onApplied: resetDraft
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 561,
                columnNumber: 9
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
                                        lineNumber: 573,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: query,
                                        onChange: (event)=>setQuery(event.target.value),
                                        placeholder: "Tìm tên, entity ID hoặc alias…"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 574,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 572,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                value: typeFilter,
                                onChange: (event)=>setTypeFilter(event.target.value),
                                "aria-label": "Lọc loại entity",
                                children: typeFilterOptions.map((type)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: type,
                                        children: type === "all" ? "Mọi loại node" : type
                                    }, type, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 586,
                                        columnNumber: 17
                                    }, this))
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 580,
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
                                        lineNumber: 594,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "missing",
                                        children: "Thiếu entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 595,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "draft",
                                        children: "Bản nháp"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 596,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "verified",
                                        children: "Đã xác minh"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 597,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 589,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: ()=>beginAddEntity(),
                                children: "＋ Thêm entity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 599,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 571,
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
                                        lineNumber: 607,
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
                                        lineNumber: 608,
                                        columnNumber: 17
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 606,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Canonical name"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 615,
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
                                        lineNumber: 615,
                                        columnNumber: 49
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 615,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Node type"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 616,
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
                                                lineNumber: 616,
                                                columnNumber: 202
                                            }, this))
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 616,
                                        columnNumber: 44
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 616,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "Trạng thái"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 617,
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
                                                lineNumber: 617,
                                                columnNumber: 176
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                value: "verified",
                                                children: "Đã xác minh"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 617,
                                                columnNumber: 215
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 617,
                                        columnNumber: 45
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 617,
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
                                        lineNumber: 618,
                                        columnNumber: 48
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "kgPrimaryButton",
                                        type: "submit",
                                        disabled: saving,
                                        children: saving ? "Đang lưu…" : "Lưu entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 618,
                                        columnNumber: 146
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 618,
                                columnNumber: 15
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 605,
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
                                                lineNumber: 625,
                                                columnNumber: 17
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                                children: [
                                                    "entities.csv: ",
                                                    persistedCount,
                                                    " records"
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 626,
                                                columnNumber: 17
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 624,
                                        columnNumber: 15
                                    }, this),
                                    filteredEntities.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "emptyState",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                children: "Không tìm thấy entity"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 630,
                                                columnNumber: 19
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                children: "Thử đổi từ khóa hoặc bộ lọc hiện tại."
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 631,
                                                columnNumber: 19
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 629,
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
                                                            lineNumber: 642,
                                                            columnNumber: 21
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: `status status-${entity.status === "missing" ? "failed" : entity.status}`,
                                                            children: STATUS_LABELS[entity.status]
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 643,
                                                            columnNumber: 21
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 641,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                                    children: entity.name
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 647,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: entity.id
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 648,
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
                                                    lineNumber: 649,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, entity.id, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 635,
                                            columnNumber: 17
                                        }, this))
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 623,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "detailPane kgInspector",
                                children: selectedEntity ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(EntityInspector, {
                                    entity: selectedEntity,
                                    properties: selectedProperties,
                                    relationships: selectedRelationships,
                                    entities: entities,
                                    nodeTypes: nodeDefinitions.map((node)=>node.type),
                                    relationshipTypes: relationshipDefinitions.map((relationship)=>relationship.type),
                                    saving: saving,
                                    issues: issues.filter((issue)=>issue.entityId === selectedEntity.id),
                                    onCreate: ()=>beginAddEntity(selectedEntity),
                                    onDelete: ()=>deleteEntity(selectedEntity),
                                    onOpenEntity: openEntity,
                                    onSaveIdentity: (input)=>saveEntityIdentity(selectedEntity.id, input),
                                    onSaveProperties: (rows)=>saveProperties([
                                            ...propertyRows.filter((property)=>property.entityId !== selectedEntity.id),
                                            ...rows
                                        ]),
                                    onSaveAliases: (values)=>saveAliases([
                                            ...aliasRows.filter((alias)=>alias.entityId !== selectedEntity.id),
                                            ...values.map((alias)=>({
                                                    entityId: selectedEntity.id,
                                                    alias,
                                                    language: /[À-ỹ]/u.test(alias) ? "vi" : "en"
                                                }))
                                        ]),
                                    onSaveRelationships: (rows)=>saveRelationships([
                                            ...relationshipRows.filter((relationship)=>!selectedRelationships.some((selected)=>selected.id === relationship.id)),
                                            ...rows
                                        ])
                                }, selectedEntity.id, false, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 656,
                                    columnNumber: 17
                                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "detailEmpty",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                            children: "Chọn một entity để kiểm tra"
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 691,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            children: "Alias, properties và raw record sẽ xuất hiện tại đây."
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 692,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 690,
                                    columnNumber: 17
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 654,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 622,
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
                lineNumber: 701,
                columnNumber: 9
            }, this),
            activeTab === "relationships" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RelationshipTable, {
                relationships: relationshipRows,
                definitions: relationshipDefinitions,
                saving: saving,
                onSave: saveRelationships
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 711,
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
                lineNumber: 720,
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
                                        lineNumber: 733,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                        children: "Validation report"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 734,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: validatedAt ? `Kiểm tra gần nhất lúc ${validatedAt.toLocaleTimeString("vi-VN")}` : "Kết quả tự động từ snapshot đang mở."
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 735,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 732,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: runValidation,
                                children: "↻ Chạy lại"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 741,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 731,
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
                                        lineNumber: 744,
                                        columnNumber: 44
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "/ 100"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 744,
                                        columnNumber: 132
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 744,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Dataset chưa sẵn sàng để publish"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 745,
                                        columnNumber: 18
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: "Xử lý lỗi contract trước, sau đó review các cảnh báo về độ đầy đủ dữ liệu."
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 745,
                                        columnNumber: 57
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 745,
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
                                lineNumber: 746,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 743,
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
                                        lineNumber: 751,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                children: issue.title
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 752,
                                                columnNumber: 22
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                children: issue.message
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 752,
                                                columnNumber: 42
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: issue.path
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 752,
                                                columnNumber: 64
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 752,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        className: `status status-${issue.severity === "error" ? "failed" : "warning"}`,
                                        children: severityLabel(issue.severity)
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 753,
                                        columnNumber: 17
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
                                        children: "→"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 754,
                                        columnNumber: 17
                                    }, this)
                                ]
                            }, issue.id, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 750,
                                columnNumber: 15
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 748,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 730,
                columnNumber: 9
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("footer", {
                className: "kgFooter",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: "Snapshot này chỉ phục vụ giao diện quản trị. Dữ liệu chưa được ghi vào PostgreSQL, Place Resolver hoặc các file nguồn cho đến khi có API admin tương ứng."
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 762,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        disabled: true,
                        title: "Cần xử lý validation issues và kết nối API lưu draft",
                        children: "Publish version"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 766,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 761,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 473,
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
                                lineNumber: 843,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "Aliases"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 844,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Mỗi alias là một dòng và được lưu trực tiếp vào aliases.csv."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 845,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 842,
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
                                lineNumber: 848,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: beginAdd,
                                children: "＋ Thêm alias"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 849,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 847,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 841,
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
                                lineNumber: 854,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: entityId,
                                onChange: (event)=>setEntityId(event.target.value),
                                placeholder: "place_001"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 854,
                                columnNumber: 40
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 854,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Alias"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 855,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: aliasValue,
                                onChange: (event)=>setAliasValue(event.target.value),
                                placeholder: "Tên địa điểm"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 855,
                                columnNumber: 36
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 855,
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
                                lineNumber: 857,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "submit",
                                disabled: saving,
                                children: saving ? "Đang lưu…" : "Lưu vào file"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 858,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 856,
                        columnNumber: 11
                    }, this),
                    formError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: formError
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 860,
                        columnNumber: 25
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 853,
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
                                        lineNumber: 865,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Ngôn ngữ"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 865,
                                        columnNumber: 36
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Entity ID"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 865,
                                        columnNumber: 53
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 865,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Thao tác"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 865,
                                        columnNumber: 86
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 865,
                                columnNumber: 18
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 865,
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
                                                lineNumber: 871,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 871,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgLanguage",
                                                children: alias.language.toUpperCase()
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 872,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 872,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: alias.entityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 873,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 873,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: `status status-${entity?.status === "missing" ? "failed" : "draft"}`,
                                                children: entity?.status === "missing" ? "Không tồn tại" : "Draft"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 874,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 874,
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
                                                        lineNumber: 875,
                                                        columnNumber: 53
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        type: "button",
                                                        onClick: ()=>onOpenEntity(alias.entityId),
                                                        children: "Mở"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 875,
                                                        columnNumber: 120
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        className: "danger",
                                                        type: "button",
                                                        onClick: ()=>removeAlias(index),
                                                        children: "Xóa"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 875,
                                                        columnNumber: 198
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 875,
                                                columnNumber: 23
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 875,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, `${alias.entityId}-${alias.alias}-${index}`, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 870,
                                    columnNumber: 17
                                }, this);
                            })
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 866,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 864,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 863,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 840,
        columnNumber: 5
    }, this);
}
function RelationshipTable({ relationships, definitions, saving, onSave }) {
    const [editingIndex, setEditingIndex] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [draft, setDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({
        fromEntityId: "",
        relationship: "LOCATED_IN",
        toEntityId: "",
        recommendations: "[]",
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
            recommendations: item.recommendations,
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
            recommendations: "[]",
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
        try {
            if (!Array.isArray(JSON.parse(draft.recommendations))) throw new Error();
        } catch  {
            setFormError("Recommendations phải là một JSON array hợp lệ.");
            return;
        }
        const nextRow = {
            id: editingIndex === "new" ? `relationship-${Date.now()}` : relationships[editingIndex].id,
            fromEntityId: draft.fromEntityId.trim(),
            relationship: draft.relationship,
            toEntityId: draft.toEntityId.trim(),
            recommendations: draft.recommendations.trim(),
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
                                lineNumber: 961,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "Relationships"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 962,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Mỗi relationship là một dòng; recommendations là JSON array có nguồn."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 963,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 960,
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
                                lineNumber: 966,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: beginAdd,
                                children: "＋ Thêm relationship"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 967,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 965,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 959,
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
                                lineNumber: 972,
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
                                lineNumber: 972,
                                columnNumber: 42
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 972,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Relationship"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 973,
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
                                        lineNumber: 973,
                                        columnNumber: 207
                                    }, this))
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 973,
                                columnNumber: 43
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 973,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "To entity"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 974,
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
                                lineNumber: 974,
                                columnNumber: 40
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 974,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Recommendations JSON"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 975,
                                columnNumber: 18
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                value: draft.recommendations,
                                onChange: (event)=>setDraft((current)=>({
                                            ...current,
                                            recommendations: event.target.value
                                        })),
                                placeholder: "[]"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 975,
                                columnNumber: 51
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 975,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Nguồn"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 976,
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
                                lineNumber: 976,
                                columnNumber: 36
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 976,
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
                                lineNumber: 978,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "submit",
                                disabled: saving,
                                children: saving ? "Đang lưu…" : "Lưu vào file"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 979,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 977,
                        columnNumber: 11
                    }, this),
                    formError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: formError
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 981,
                        columnNumber: 25
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 971,
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
                                        lineNumber: 986,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Relationship"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 986,
                                        columnNumber: 35
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "To"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 986,
                                        columnNumber: 56
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Recommendations"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 986,
                                        columnNumber: 67
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Nguồn"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 986,
                                        columnNumber: 91
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Thao tác"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 986,
                                        columnNumber: 105
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 986,
                                columnNumber: 18
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 986,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                            children: relationships.length === 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                className: "kgEmptyRow",
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                    colSpan: 6,
                                    children: "relationships.csv chưa có bản ghi. Bấm “Thêm relationship” để tạo dòng đầu tiên."
                                }, void 0, false, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 989,
                                    columnNumber: 42
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 989,
                                columnNumber: 15
                            }, this) : relationships.map((relationship, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: relationship.fromEntityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 992,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 992,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgRelationBadge",
                                                children: relationship.relationship
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 993,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 993,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: relationship.toEntityId
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 994,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 994,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RecommendationView, {
                                                value: relationship.recommendations,
                                                compact: true
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 995,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 995,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgSourceCell",
                                                title: relationship.source,
                                                children: relationship.source
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 996,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 996,
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
                                                        lineNumber: 997,
                                                        columnNumber: 51
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        className: "danger",
                                                        type: "button",
                                                        onClick: ()=>removeRelationship(index),
                                                        children: "Xóa"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 997,
                                                        columnNumber: 118
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 997,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 997,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, relationship.id, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 991,
                                    columnNumber: 15
                                }, this))
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 987,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 985,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 984,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 958,
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
                                lineNumber: 1117,
                                columnNumber: 14
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: "Schema & Ontology"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1117,
                                columnNumber: 56
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "Mỗi node hoặc relationship type là một dòng compact."
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1117,
                                columnNumber: 82
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1117,
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
                                lineNumber: 1118,
                                columnNumber: 41
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgSecondaryButton",
                                type: "button",
                                onClick: addNode,
                                children: "＋ Node"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1118,
                                columnNumber: 99
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "button",
                                onClick: addRelationship,
                                children: "＋ Relationship"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1118,
                                columnNumber: 184
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1118,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1116,
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
                                lineNumber: 1122,
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
                                lineNumber: 1122,
                                columnNumber: 73
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1122,
                        columnNumber: 45
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: "Mô tả"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1123,
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
                                lineNumber: 1123,
                                columnNumber: 36
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1123,
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
                                        lineNumber: 1125,
                                        columnNumber: 20
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: draft.from,
                                        onChange: (event)=>setDraft((current)=>({
                                                    ...current,
                                                    from: event.target.value
                                                })),
                                        placeholder: "Area|Place"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1125,
                                        columnNumber: 42
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1125,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "To type"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1126,
                                        columnNumber: 20
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                        value: draft.to,
                                        onChange: (event)=>setDraft((current)=>({
                                                    ...current,
                                                    to: event.target.value
                                                })),
                                        placeholder: "TravelPlace|Restaurant"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1126,
                                        columnNumber: 40
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1126,
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
                                lineNumber: 1128,
                                columnNumber: 44
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                className: "kgPrimaryButton",
                                type: "submit",
                                disabled: saving,
                                children: saving ? "Đang lưu…" : "Lưu ontology"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1128,
                                columnNumber: 138
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1128,
                        columnNumber: 11
                    }, this),
                    formError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: formError
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1129,
                        columnNumber: 25
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1121,
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
                                        lineNumber: 1134,
                                        columnNumber: 22
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Tên"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1134,
                                        columnNumber: 35
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "From"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1134,
                                        columnNumber: 47
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "To"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1134,
                                        columnNumber: 60
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Mô tả"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1134,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Trạng thái"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1134,
                                        columnNumber: 85
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                        children: "Thao tác"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1134,
                                        columnNumber: 104
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1134,
                                columnNumber: 18
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1134,
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
                                                    lineNumber: 1136,
                                                    columnNumber: 68
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
                                                columnNumber: 64
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("strong", {
                                                    children: node.type
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1136,
                                                    columnNumber: 117
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
                                                columnNumber: 113
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: "—"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
                                                columnNumber: 150
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: "—"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
                                                columnNumber: 160
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: node.description ?? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgMissingText",
                                                    children: "Chưa có mô tả"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1136,
                                                    columnNumber: 195
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
                                                columnNumber: 170
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: `status status-${node.description ? "completed" : "warning"}`,
                                                    children: node.description ? "Defined" : "Missing"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1136,
                                                    columnNumber: 257
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
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
                                                            lineNumber: 1136,
                                                            columnNumber: 425
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            className: "danger",
                                                            type: "button",
                                                            onClick: ()=>removeNode(node),
                                                            children: "Xóa"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1136,
                                                            columnNumber: 490
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1136,
                                                    columnNumber: 395
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1136,
                                                columnNumber: 391
                                            }, this)
                                        ]
                                    }, `node-${node.type}`, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1136,
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
                                                    lineNumber: 1137,
                                                    columnNumber: 100
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
                                                columnNumber: 96
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: relationship.type
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1137,
                                                    columnNumber: 149
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
                                                columnNumber: 145
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: relationship.from ?? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgMissingText",
                                                    children: "?"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1137,
                                                    columnNumber: 212
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
                                                columnNumber: 186
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: relationship.to ?? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "kgMissingText",
                                                    children: "?"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1137,
                                                    columnNumber: 282
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
                                                columnNumber: 258
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: relationship.description
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
                                                columnNumber: 328
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: `status status-${relationship.from && relationship.to ? "completed" : "failed"}`,
                                                    children: relationship.from && relationship.to ? "Defined" : "Incomplete"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1137,
                                                    columnNumber: 367
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
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
                                                            lineNumber: 1137,
                                                            columnNumber: 577
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                            className: "danger",
                                                            type: "button",
                                                            onClick: ()=>removeOntologyRelationship(relationship),
                                                            children: "Xóa"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1137,
                                                            columnNumber: 658
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1137,
                                                    columnNumber: 547
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1137,
                                                columnNumber: 543
                                            }, this)
                                        ]
                                    }, `relationship-${relationship.type}`, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1137,
                                        columnNumber: 50
                                    }, this))
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                            lineNumber: 1135,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1133,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1132,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("details", {
                className: "kgSchemaDetails",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("summary", {
                        children: "Xem schema.yaml"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1141,
                        columnNumber: 44
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RawFile, {
                        name: "schema.yaml",
                        value: rawSchema
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1141,
                        columnNumber: 78
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1141,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1115,
        columnNumber: 5
    }, this);
}
function EntityInspector({ entity, properties, relationships, entities, nodeTypes, relationshipTypes, saving, issues, onCreate, onDelete, onOpenEntity, onSaveIdentity, onSaveProperties, onSaveAliases, onSaveRelationships }) {
    const [editing, setEditing] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [sectionError, setSectionError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [identityDraft, setIdentityDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({
        name: entity.name,
        type: entity.type,
        status: entity.status
    });
    const [propertyDraft, setPropertyDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(properties.map((property)=>({
            ...property
        })));
    const [aliasDraft, setAliasDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([
        ...entity.aliases
    ]);
    const [relationshipDraft, setRelationshipDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(relationships.map((relationship)=>({
            ...relationship
        })));
    function beginSection(section) {
        setSectionError("");
        if (section === "identity") setIdentityDraft({
            name: entity.name,
            type: entity.type,
            status: entity.status
        });
        if (section === "properties") setPropertyDraft(properties.map((property)=>({
                ...property
            })));
        if (section === "aliases") setAliasDraft([
            ...entity.aliases
        ]);
        if (section === "relationships") setRelationshipDraft(relationships.map((relationship)=>({
                ...relationship
            })));
        setEditing(section);
    }
    async function saveSection(section) {
        setSectionError("");
        try {
            if (section === "identity") {
                if (!identityDraft.name.trim() || !identityDraft.type.trim()) throw new Error("Tên và node type là bắt buộc.");
                await onSaveIdentity({
                    ...identityDraft,
                    name: identityDraft.name.trim()
                });
            }
            if (section === "properties") {
                if (propertyDraft.some((row)=>!row.key.trim() || !row.source.trim())) throw new Error("Mỗi property phải có key và nguồn.");
                const keys = propertyDraft.map((row)=>row.key.trim());
                if (new Set(keys).size !== keys.length) throw new Error("Key property không được trùng trong cùng entity.");
                const specialExperienceRow = propertyDraft.find((row)=>row.key.trim() === "special_experience");
                if (specialExperienceRow) {
                    try {
                        if (!Array.isArray(JSON.parse(specialExperienceRow.value))) throw new Error();
                    } catch  {
                        throw new Error("Property special_experience phải là một JSON array hợp lệ.");
                    }
                }
                await onSaveProperties(propertyDraft.map((row)=>({
                        ...row,
                        entityId: entity.id,
                        key: row.key.trim(),
                        source: row.source.trim()
                    })));
            }
            if (section === "aliases") {
                const values = aliasDraft.map((value)=>value.trim()).filter(Boolean);
                if (new Set(values).size !== values.length) throw new Error("Alias không được trùng trong cùng entity.");
                await onSaveAliases(values);
            }
            if (section === "relationships") {
                if (relationshipDraft.some((row)=>!row.fromEntityId || !row.relationship || !row.toEntityId || !row.source.trim())) {
                    throw new Error("From, relationship, to và nguồn là bắt buộc.");
                }
                if (relationshipDraft.some((row)=>{
                    try {
                        return !Array.isArray(JSON.parse(row.recommendations));
                    } catch  {
                        return true;
                    }
                })) throw new Error("Recommendations của mỗi relationship phải là JSON array hợp lệ.");
                await onSaveRelationships(relationshipDraft.map((row)=>({
                        ...row,
                        source: row.source.trim()
                    })));
            }
            setEditing(null);
        } catch (error) {
            setSectionError(error instanceof Error ? error.message : "Không lưu được thay đổi.");
        }
    }
    function sectionActions(section) {
        if (editing !== section) {
            return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                className: "kgSectionEdit",
                type: "button",
                disabled: editing !== null || entity.status === "missing",
                onClick: ()=>beginSection(section),
                children: "Sửa"
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1243,
                columnNumber: 14
            }, this);
        }
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
            className: "kgSectionActions",
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                    type: "button",
                    disabled: saving,
                    onClick: ()=>setEditing(null),
                    children: "Hủy"
                }, void 0, false, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1247,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                    className: "save",
                    type: "button",
                    disabled: saving,
                    onClick: ()=>void saveSection(section),
                    children: saving ? "Đang lưu…" : "Lưu"
                }, void 0, false, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1248,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
            lineNumber: 1246,
            columnNumber: 7
        }, this);
    }
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
                                lineNumber: 1257,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                children: entity.name
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1258,
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
                                lineNumber: 1259,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1256,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: `status status-${entity.status === "missing" ? "failed" : entity.status}`,
                        children: STATUS_LABELS[entity.status]
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1261,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1255,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "kgInspectorBody kgInspectorAll",
                children: [
                    issues.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgInlineIssues",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                children: "Validation issues"
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1267,
                                columnNumber: 13
                            }, this),
                            issues.map((issue)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            children: "!"
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1268,
                                            columnNumber: 54
                                        }, this),
                                        issue.message
                                    ]
                                }, issue.id, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 1268,
                                    columnNumber: 36
                                }, this))
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1266,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "kgDefinitionList kgInspectorSection",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                        children: "Thông tin entity"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1274,
                                        columnNumber: 13
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgSectionHeaderActions",
                                        children: entity.status === "missing" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            className: "kgSectionEdit",
                                            type: "button",
                                            onClick: onCreate,
                                            children: "Tạo entity"
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1277,
                                            columnNumber: 17
                                        }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                                            children: [
                                                sectionActions("identity"),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    className: "kgSectionDelete",
                                                    type: "button",
                                                    disabled: editing !== null || saving,
                                                    onClick: onDelete,
                                                    children: "Xóa"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1279,
                                                    columnNumber: 47
                                                }, this)
                                            ]
                                        }, void 0, true)
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1275,
                                        columnNumber: 13
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1273,
                                columnNumber: 11
                            }, this),
                            editing === "identity" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgSectionForm kgIdentitySectionForm",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: "Canonical ID"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1285,
                                                columnNumber: 22
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                value: entity.id,
                                                disabled: true
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1285,
                                                columnNumber: 47
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1285,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: "Canonical name"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1286,
                                                columnNumber: 22
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                value: identityDraft.name,
                                                onChange: (event)=>setIdentityDraft((current)=>({
                                                            ...current,
                                                            name: event.target.value
                                                        }))
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1286,
                                                columnNumber: 49
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1286,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: "Node type"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1287,
                                                columnNumber: 22
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                                value: identityDraft.type,
                                                onChange: (event)=>setIdentityDraft((current)=>({
                                                            ...current,
                                                            type: event.target.value
                                                        })),
                                                children: nodeTypes.map((type)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                        value: type,
                                                        children: type
                                                    }, type, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1287,
                                                        columnNumber: 200
                                                    }, this))
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1287,
                                                columnNumber: 44
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1287,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: "Trạng thái"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1288,
                                                columnNumber: 22
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                                value: identityDraft.status,
                                                onChange: (event)=>setIdentityDraft((current)=>({
                                                            ...current,
                                                            status: event.target.value
                                                        })),
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                        value: "draft",
                                                        children: "Bản nháp"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1288,
                                                        columnNumber: 205
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                        value: "verified",
                                                        children: "Đã xác minh"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1288,
                                                        columnNumber: 244
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1288,
                                                columnNumber: 45
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1288,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1284,
                                columnNumber: 13
                            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dl", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Canonical name"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1292,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: entity.name
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1292,
                                                columnNumber: 43
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1292,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Canonical ID"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1293,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: entity.id
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1293,
                                                    columnNumber: 45
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1293,
                                                columnNumber: 41
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1293,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Node type"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1294,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: entity.type
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1294,
                                                columnNumber: 38
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1294,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Status"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1295,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: STATUS_LABELS[entity.status]
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1295,
                                                columnNumber: 35
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1295,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dt", {
                                                children: "Source file"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1296,
                                                columnNumber: 20
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("dd", {
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                    children: entity.sourceFile
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1296,
                                                    columnNumber: 44
                                                }, this)
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1296,
                                                columnNumber: 40
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1296,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1291,
                                columnNumber: 13
                            }, this),
                            editing === "identity" && sectionError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgSectionError",
                                children: sectionError
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1299,
                                columnNumber: 54
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1272,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "kgInspectorSection",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                        children: "Properties"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1303,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgSectionHeaderActions",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgSectionCount",
                                                children: properties.length
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1303,
                                                columnNumber: 78
                                            }, this),
                                            sectionActions("properties")
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1303,
                                        columnNumber: 38
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1303,
                                columnNumber: 11
                            }, this),
                            editing === "properties" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgSectionEditList",
                                children: [
                                    propertyDraft.map((property, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgPropertyEditRow",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    "aria-label": "Property key",
                                                    value: property.key,
                                                    onChange: (event)=>setPropertyDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    key: event.target.value
                                                                } : row)),
                                                    placeholder: "key"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1308,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    "aria-label": "Property value",
                                                    value: property.value,
                                                    onChange: (event)=>setPropertyDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    value: event.target.value
                                                                } : row)),
                                                    placeholder: "value"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1309,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    "aria-label": "Property source",
                                                    value: property.source,
                                                    onChange: (event)=>setPropertyDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    source: event.target.value
                                                                } : row)),
                                                    placeholder: "Nguồn"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1310,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    className: "kgMiniDanger",
                                                    type: "button",
                                                    onClick: ()=>setPropertyDraft((current)=>current.filter((_, rowIndex)=>rowIndex !== index)),
                                                    children: "×"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1311,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, `${property.key}-${index}`, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1307,
                                            columnNumber: 17
                                        }, this)),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "kgAddRowButton",
                                        type: "button",
                                        onClick: ()=>setPropertyDraft((current)=>[
                                                    ...current,
                                                    {
                                                        entityId: entity.id,
                                                        key: "",
                                                        value: "",
                                                        source: ""
                                                    }
                                                ]),
                                        children: "＋ Thêm property"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1314,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1305,
                                columnNumber: 13
                            }, this) : properties.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgPropertyTableWrap",
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
                                    className: "kgPropertyTable",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                                        children: "Key"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1319,
                                                        columnNumber: 28
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                                        children: "Value"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1319,
                                                        columnNumber: 40
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                                                        children: "Nguồn"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1319,
                                                        columnNumber: 54
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1319,
                                                columnNumber: 24
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1319,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                                            children: properties.map((property, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                                children: property.key
                                                            }, void 0, false, {
                                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                                lineNumber: 1323,
                                                                columnNumber: 27
                                                            }, this)
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1323,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                            children: property.key === "special_experience" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RecommendationView, {
                                                                value: property.value
                                                            }, void 0, false, {
                                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                                lineNumber: 1324,
                                                                columnNumber: 68
                                                            }, this) : property.value || /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                className: "kgMissingText",
                                                                children: "Trống"
                                                            }, void 0, false, {
                                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                                lineNumber: 1324,
                                                                columnNumber: 134
                                                            }, this)
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1324,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(SourceValue, {
                                                                source: property.source
                                                            }, void 0, false, {
                                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                                lineNumber: 1325,
                                                                columnNumber: 27
                                                            }, this)
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1325,
                                                            columnNumber: 23
                                                        }, this)
                                                    ]
                                                }, `${property.key}-${index}`, true, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1322,
                                                    columnNumber: 21
                                                }, this))
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1320,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 1318,
                                    columnNumber: 15
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1317,
                                columnNumber: 13
                            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgInspectorEmpty kgInspectorEmptyCompact",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "◇"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1332,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Chưa có property"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1332,
                                        columnNumber: 85
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: "Không có dòng tương ứng trong properties.csv."
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1332,
                                        columnNumber: 108
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1332,
                                columnNumber: 13
                            }, this),
                            editing === "properties" && sectionError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgSectionError",
                                children: sectionError
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1334,
                                columnNumber: 56
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1302,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "kgInspectorSection",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                        children: "Aliases"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1338,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgSectionHeaderActions",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgSectionCount",
                                                children: entity.aliases.length
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1338,
                                                columnNumber: 75
                                            }, this),
                                            sectionActions("aliases")
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1338,
                                        columnNumber: 35
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1338,
                                columnNumber: 11
                            }, this),
                            editing === "aliases" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgSectionEditList",
                                children: [
                                    aliasDraft.map((alias, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgAliasEditRow",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    "aria-label": `Alias ${index + 1}`,
                                                    value: alias,
                                                    onChange: (event)=>setAliasDraft((current)=>current.map((value, rowIndex)=>rowIndex === index ? event.target.value : value)),
                                                    placeholder: "Alias"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1343,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    className: "kgMiniDanger",
                                                    type: "button",
                                                    onClick: ()=>setAliasDraft((current)=>current.filter((_, rowIndex)=>rowIndex !== index)),
                                                    children: "×"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1344,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, `${alias}-${index}`, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1342,
                                            columnNumber: 17
                                        }, this)),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "kgAddRowButton",
                                        type: "button",
                                        onClick: ()=>setAliasDraft((current)=>[
                                                    ...current,
                                                    ""
                                                ]),
                                        children: "＋ Thêm alias"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1347,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1340,
                                columnNumber: 13
                            }, this) : entity.aliases.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgAliasCards",
                                children: entity.aliases.map((alias, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                children: index + 1
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1352,
                                                columnNumber: 52
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                        children: alias
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1352,
                                                        columnNumber: 81
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                                        children: /[À-ỹ]/u.test(alias) ? "Vietnamese" : "Other"
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1352,
                                                        columnNumber: 95
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1352,
                                                columnNumber: 76
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                children: "aliases.csv"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1352,
                                                columnNumber: 163
                                            }, this)
                                        ]
                                    }, `${alias}-${index}`, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1352,
                                        columnNumber: 17
                                    }, this))
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1350,
                                columnNumber: 13
                            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgInspectorEmpty kgInspectorEmptyCompact",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "◇"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1356,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Chưa có alias"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1356,
                                        columnNumber: 85
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1356,
                                columnNumber: 13
                            }, this),
                            editing === "aliases" && sectionError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgSectionError",
                                children: sectionError
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1358,
                                columnNumber: 53
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1337,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
                        className: "kgInspectorSection",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                        children: "Relationships"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1362,
                                        columnNumber: 19
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        className: "kgSectionHeaderActions",
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: "kgSectionCount",
                                                children: relationships.length
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1362,
                                                columnNumber: 81
                                            }, this),
                                            sectionActions("relationships")
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1362,
                                        columnNumber: 41
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1362,
                                columnNumber: 11
                            }, this),
                            editing === "relationships" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgSectionEditList",
                                children: [
                                    relationshipDraft.map((relationship, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "kgRelationshipEditRow",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                                    "aria-label": "From entity",
                                                    value: relationship.fromEntityId,
                                                    onChange: (event)=>setRelationshipDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    fromEntityId: event.target.value
                                                                } : row)),
                                                    children: entities.filter((item)=>item.status !== "missing").map((item)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                            value: item.id,
                                                            children: item.name
                                                        }, item.id, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1367,
                                                            columnNumber: 315
                                                        }, this))
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1367,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                                    "aria-label": "Relationship type",
                                                    value: relationship.relationship,
                                                    onChange: (event)=>setRelationshipDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    relationship: event.target.value
                                                                } : row)),
                                                    children: relationshipTypes.map((type)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                            value: type,
                                                            children: type
                                                        }, type, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1368,
                                                            columnNumber: 286
                                                        }, this))
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1368,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                                    "aria-label": "To entity",
                                                    value: relationship.toEntityId,
                                                    onChange: (event)=>setRelationshipDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    toEntityId: event.target.value
                                                                } : row)),
                                                    children: entities.filter((item)=>item.status !== "missing").map((item)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                                            value: item.id,
                                                            children: item.name
                                                        }, item.id, false, {
                                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                            lineNumber: 1369,
                                                            columnNumber: 309
                                                        }, this))
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1369,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    "aria-label": "Relationship recommendations",
                                                    value: relationship.recommendations,
                                                    onChange: (event)=>setRelationshipDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    recommendations: event.target.value
                                                                } : row)),
                                                    placeholder: "Recommendations JSON array"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1370,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    "aria-label": "Relationship source",
                                                    value: relationship.source,
                                                    onChange: (event)=>setRelationshipDraft((current)=>current.map((row, rowIndex)=>rowIndex === index ? {
                                                                    ...row,
                                                                    source: event.target.value
                                                                } : row)),
                                                    placeholder: "Nguồn"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1371,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    className: "kgMiniDanger",
                                                    type: "button",
                                                    onClick: ()=>setRelationshipDraft((current)=>current.filter((_, rowIndex)=>rowIndex !== index)),
                                                    children: "×"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                    lineNumber: 1372,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, relationship.id, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1366,
                                            columnNumber: 17
                                        }, this)),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "kgAddRowButton",
                                        type: "button",
                                        onClick: ()=>setRelationshipDraft((current)=>[
                                                    ...current,
                                                    {
                                                        id: `relationship-new-${Date.now()}-${current.length}`,
                                                        fromEntityId: entity.id,
                                                        relationship: relationshipTypes[0] ?? "",
                                                        toEntityId: entities.find((item)=>item.id !== entity.id && item.status !== "missing")?.id ?? entity.id,
                                                        recommendations: "[]",
                                                        source: ""
                                                    }
                                                ]),
                                        children: "＋ Thêm relationship"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1375,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1364,
                                columnNumber: 13
                            }, this) : relationships.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgRelationCards",
                                children: relationships.map((relationship)=>{
                                    const outgoing = relationship.fromEntityId === entity.id;
                                    const relatedId = outgoing ? relationship.toEntityId : relationship.fromEntityId;
                                    const relatedEntity = entities.find((item)=>item.id === relatedId);
                                    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                className: `kgRelationDirection ${outgoing ? "outgoing" : "incoming"}`,
                                                children: outgoing ? "OUT" : "IN"
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1392,
                                                columnNumber: 21
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                                                        children: relationship.relationship
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1394,
                                                        columnNumber: 23
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                        type: "button",
                                                        onClick: ()=>onOpenEntity(relatedId),
                                                        children: relatedEntity?.name ?? relatedId
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1395,
                                                        columnNumber: 23
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                                        children: outgoing ? `${entity.id} → ${relatedId}` : `${relatedId} → ${entity.id}`
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1396,
                                                        columnNumber: 23
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(RecommendationView, {
                                                        value: relationship.recommendations
                                                    }, void 0, false, {
                                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                        lineNumber: 1397,
                                                        columnNumber: 23
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1393,
                                                columnNumber: 21
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(SourceValue, {
                                                source: relationship.source
                                            }, void 0, false, {
                                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                                lineNumber: 1399,
                                                columnNumber: 21
                                            }, this)
                                        ]
                                    }, relationship.id, true, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1391,
                                        columnNumber: 19
                                    }, this);
                                })
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1385,
                                columnNumber: 13
                            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "kgInspectorEmpty kgInspectorEmptyCompact",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "◇"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1405,
                                        columnNumber: 71
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                        children: "Chưa có relationship"
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1405,
                                        columnNumber: 85
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                        children: "Entity này chưa được nối với node nào khác."
                                    }, void 0, false, {
                                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                        lineNumber: 1405,
                                        columnNumber: 112
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1405,
                                columnNumber: 13
                            }, this),
                            editing === "relationships" && sectionError && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "kgSectionError",
                                children: sectionError
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1407,
                                columnNumber: 59
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1361,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1264,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true);
}
function SourceValue({ source }) {
    if (!source) return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: "kgMissingText",
        children: "Thiếu nguồn"
    }, void 0, false, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1415,
        columnNumber: 23
    }, this);
    if (/^https?:\/\//i.test(source)) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
            className: "kgSourceLink",
            href: source,
            target: "_blank",
            rel: "noreferrer",
            children: "Mở nguồn ↗"
        }, void 0, false, {
            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
            lineNumber: 1417,
            columnNumber: 12
        }, this);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
        className: "kgSourceCode",
        children: source
    }, void 0, false, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1419,
        columnNumber: 10
    }, this);
}
function RecommendationView({ value, compact = false }) {
    let items;
    try {
        const parsed = JSON.parse(value);
        if (!Array.isArray(parsed)) throw new Error();
        items = parsed.filter((item)=>Boolean(item) && typeof item === "object" && !Array.isArray(item));
    } catch  {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
            className: "kgRecommendationInvalid",
            children: "JSON không hợp lệ"
        }, void 0, false, {
            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
            lineNumber: 1429,
            columnNumber: 12
        }, this);
    }
    if (items.length === 0) return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: "kgMissingText",
        children: "Không có recommendation"
    }, void 0, false, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1431,
        columnNumber: 34
    }, this);
    const intentLabels = {
        visit: "Tham quan",
        eat: "Ăn uống",
        drink: "Đồ uống",
        stay: "Lưu trú",
        transfer: "Di chuyển",
        combine_visit: "Kết hợp tham quan",
        explore: "Khám phá"
    };
    const priorityLabels = {
        must: "Phải thử",
        recommended: "Nên thử",
        optional: "Tùy chọn"
    };
    if (compact) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "kgRecommendationCompact",
            children: items.map((item, index)=>{
                const intent = String(item.intent ?? "recommend");
                const priority = String(item.priority ?? "");
                return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                    children: [
                        intentLabels[intent] ?? intent,
                        priority ? ` · ${priorityLabels[priority] ?? priority}` : ""
                    ]
                }, index, true, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1450,
                    columnNumber: 14
                }, this);
            })
        }, void 0, false, {
            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
            lineNumber: 1447,
            columnNumber: 12
        }, this);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "kgRecommendationList",
        children: items.map((item, index)=>{
            const intent = String(item.intent ?? `recommend ${index + 1}`);
            const priority = String(item.priority ?? "");
            const timeSlots = Array.isArray(item.timeSlots) ? item.timeSlots.filter((slot)=>Boolean(slot) && typeof slot === "object" && !Array.isArray(slot)) : [];
            const recommendedItems = Array.isArray(item.recommendedItems) ? item.recommendedItems : [];
            const hiddenKeys = new Set([
                "intent",
                "priority",
                "reason",
                "timeSlots",
                "recommendedItems"
            ]);
            const metadata = Object.entries(item).filter(([key])=>!hiddenKeys.has(key));
            return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("article", {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                children: intentLabels[intent] ?? intent
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1466,
                                columnNumber: 21
                            }, this),
                            priority && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: priorityLabels[priority] ?? priority
                            }, void 0, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1466,
                                columnNumber: 73
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1466,
                        columnNumber: 13
                    }, this),
                    typeof item.reason === "string" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: item.reason
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1467,
                        columnNumber: 49
                    }, this),
                    (metadata.length > 0 || timeSlots.length > 0) && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgRecommendationFacts",
                        children: [
                            metadata.map(([key, metadataValue])=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                            children: key === "recommendedVisitMinutes" ? "Thời lượng" : key
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1471,
                                            columnNumber: 35
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                            children: key === "recommendedVisitMinutes" ? `${String(metadataValue)} phút` : Array.isArray(metadataValue) ? metadataValue.join(", ") : typeof metadataValue === "object" ? JSON.stringify(metadataValue) : String(metadataValue)
                                        }, void 0, false, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1471,
                                            columnNumber: 106
                                        }, this)
                                    ]
                                }, key, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 1471,
                                    columnNumber: 19
                                }, this)),
                            timeSlots.map((slot, slotIndex)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                                            children: [
                                                "Khung giờ ",
                                                slotIndex + 1
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1473,
                                            columnNumber: 75
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                            children: [
                                                String(slot.start ?? "?"),
                                                " – ",
                                                String(slot.end ?? "?")
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                            lineNumber: 1473,
                                            columnNumber: 115
                                        }, this)
                                    ]
                                }, slotIndex, true, {
                                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                    lineNumber: 1473,
                                    columnNumber: 53
                                }, this))
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1469,
                        columnNumber: 15
                    }, this),
                    recommendedItems.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "kgRecommendedItems",
                        children: recommendedItems.map((recommendedItem, itemIndex)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: String(recommendedItem)
                            }, itemIndex, false, {
                                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                                lineNumber: 1476,
                                columnNumber: 135
                            }, this))
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1476,
                        columnNumber: 45
                    }, this)
                ]
            }, index, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1465,
                columnNumber: 11
            }, this);
        })
    }, void 0, false, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1454,
        columnNumber: 5
    }, this);
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
                        lineNumber: 1487,
                        columnNumber: 15
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("small", {
                        children: value ? `${value.split("\n").length} lines` : "EMPTY"
                    }, void 0, false, {
                        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                        lineNumber: 1487,
                        columnNumber: 34
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1487,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("pre", {
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("code", {
                    children: value || "// File is empty"
                }, void 0, false, {
                    fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                    lineNumber: 1488,
                    columnNumber: 12
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
                lineNumber: 1488,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/(dashboard)/knowledge-graph/page.tsx",
        lineNumber: 1486,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=_c91d1aa3._.js.map