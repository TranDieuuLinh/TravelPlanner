export type KnowledgeEntityType =
  | "TravelPlace"
  | "Restaurant"
  | "DrinkDessert"
  | "Accommodation"
  | "Area"
  | "Activity"
  | (string & {});

export type KnowledgeEntityStatus = "missing" | "draft" | "verified";

export type KnowledgeEntity = {
  id: string;
  name: string;
  type: KnowledgeEntityType;
  status: KnowledgeEntityStatus;
  aliases: string[];
  properties: Record<string, string>;
  sourceFile: string;
};

export type KnowledgeAlias = {
  entityId: string;
  alias: string;
  language: "vi" | "en";
};

export type KnowledgeProperty = {
  entityId: string;
  key: string;
  value: string;
  source: string;
};

export type KnowledgeRelationship = {
  id: string;
  fromEntityId: string;
  relationship: string;
  toEntityId: string;
  recommendations: string;
  source: string;
};

export type OntologyNode = {
  type: KnowledgeEntityType;
  description: string | null;
};

export type OntologyRelationship = {
  type: string;
  from: KnowledgeEntityType | null;
  to: KnowledgeEntityType | null;
  description: string;
};

export type NodeTypeDefinition = {
  abstract: boolean;
  extends: string | null;
  requiredProperties: string[];
  optionalProperties: string[];
};

export type ValidationIssue = {
  id: string;
  severity: "error" | "warning" | "info";
  title: string;
  message: string;
  path: string;
  entityId?: string;
  target: "entities" | "aliases" | "relationships" | "ontology";
};

export const initialEntities: KnowledgeEntity[] = [
  {
    id: "place_001",
    name: "Hồ Hoàn Kiếm",
    type: "TravelPlace",
    status: "missing",
    aliases: ["Hồ Hoàn Kiếm", "Hoan Kiem Lake"],
    properties: {},
    sourceFile: "aliases.csv"
  },
  {
    id: "restaurant_001",
    name: "Bún Chả Obama",
    type: "Restaurant",
    status: "missing",
    aliases: ["Bún Chả Obama"],
    properties: {},
    sourceFile: "aliases.csv"
  }
];

export const aliases: KnowledgeAlias[] = [
  { entityId: "place_001", alias: "Hồ Hoàn Kiếm", language: "vi" },
  { entityId: "place_001", alias: "Hoan Kiem Lake", language: "en" },
  { entityId: "restaurant_001", alias: "Bún Chả Obama", language: "vi" }
];

export const ontologyNodes: OntologyNode[] = [
  { type: "TravelPlace", description: "Điểm tham quan, di tích lịch sử, danh thắng tự nhiên và khu trải nghiệm du lịch" },
  { type: "Restaurant", description: "Nhà hàng, quán ăn phục vụ bữa chính" },
  { type: "DrinkDessert", description: "Quán nước, quán cà phê, tiệm trà sữa, tiệm chè, bánh ngọt và đồ ăn vặt tráng miệng" },
  { type: "Accommodation", description: "Cơ sở lưu trú du lịch (khách sạn, resort, homestay, villa, nhà nghỉ)" },
  { type: "Area", description: "Khu vực địa lý ở bất kỳ cấp nào" },
  { type: "Activity", description: "Hoạt động hoặc trải nghiệm du lịch như săn mây hoặc thưởng thức cà phê trứng" }
];

export const ontologyRelationships: OntologyRelationship[] = [
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

export const rawDataset = {
  "aliases.csv": "entity_id,alias\nplace_001,Hồ Hoàn Kiếm\nplace_001,Hoan Kiem Lake\nrestaurant_001,Bún Chả Obama",
  "entities.csv": "id,name,type,status\n",
  "ontology.yaml": "TravelPlace:\n  description: Điểm tham quan\n\nArea:\n  description: Khu vực địa lý\n\nLOCATED_IN:\n  from: Place\n  to: Area",
  "properties.csv": "entity_id,key,value,source\n",
  "relationships.csv": "id,from_entity_id,relationship,to_entity_id,recommendations,source\n",
  "schema.yaml": "nodes:\n  - TravelPlace\n  - Area\n\nrelationships:\n  - LOCATED_IN\n\nnode_type_definitions:\n  Entity:\n    abstract: true\n  LocationEntity:\n    abstract: true\n    extends: Entity\n  Place:\n    abstract: true\n    extends: LocationEntity\n  TravelPlace:\n    extends: Place\n  Area:\n    extends: LocationEntity"
};

function parseCsvRows(content: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < content.length; index += 1) {
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
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    if (row.some((value) => value.length > 0)) rows.push(row);
  }
  return rows;
}

function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export function parseAliases(content: string): KnowledgeAlias[] {
  return parseCsvRows(content)
    .slice(1)
    .filter((row) => row[0]?.trim() && row[1]?.trim())
    .map((row) => ({
      entityId: row[0].trim(),
      alias: row[1].trim(),
      language: /[À-ỹ]/u.test(row[1]) ? "vi" : "en"
    }));
}

export function serializeAliases(items: KnowledgeAlias[]): string {
  return [
    "entity_id,alias",
    ...items.map((item) => [item.entityId, item.alias].map(csvCell).join(","))
  ].join("\r\n");
}

export function parseProperties(content: string): KnowledgeProperty[] {
  return parseCsvRows(content)
    .slice(1)
    .filter((row) => row[0]?.trim() && row[1]?.trim())
    .map((row) => ({
      entityId: row[0].trim(),
      key: row[1].trim(),
      value: row[2]?.trim() ?? "",
      source: row[3]?.trim() ?? ""
    }));
}

export function serializeProperties(items: KnowledgeProperty[]): string {
  return [
    "entity_id,key,value,source",
    ...items.map((item) =>
      [item.entityId, item.key, item.value, item.source].map(csvCell).join(",")
    )
  ].join("\r\n");
}

export function parseEntities(content: string): KnowledgeEntity[] {
  return parseCsvRows(content)
    .slice(1)
    .filter((row) => row[0]?.trim() && row[1]?.trim() && row[2]?.trim())
    .map((row) => ({
      id: row[0].trim(),
      name: row[1].trim(),
      type: row[2].trim() as KnowledgeEntityType,
      status: row[3]?.trim() === "verified" ? "verified" : "draft",
      aliases: [],
      properties: {},
      sourceFile: "entities.csv"
    }));
}

export function serializeEntities(items: KnowledgeEntity[]): string {
  return [
    "id,name,type,status",
    ...items
      .filter((item) => item.status !== "missing")
      .map((item) => [item.id, item.name, item.type, item.status].map(csvCell).join(","))
  ].join("\r\n");
}

export function parseRelationships(content: string): KnowledgeRelationship[] {
  const rows = parseCsvRows(content);
  const header = rows[0] ?? [];
  const indexOf = (name: string) => header.indexOf(name);
  const modern = indexOf("id") >= 0;
  return rows.slice(1)
    .filter((row) => {
      const offset = modern ? 1 : 0;
      return row[offset]?.trim() && row[offset + 1]?.trim() && row[offset + 2]?.trim();
    })
    .map((row, index) => {
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

export function serializeRelationships(items: KnowledgeRelationship[]): string {
  return [
    "id,from_entity_id,relationship,to_entity_id,recommendations,source",
    ...items.map((item) =>
      [item.id, item.fromEntityId, item.relationship, item.toEntityId, item.recommendations, item.source]
        .map(csvCell)
        .join(",")
    )
  ].join("\r\n");
}

export function parseOntology(content: string): {
  nodes: OntologyNode[];
  relationships: OntologyRelationship[];
} {
  const blocks = content
    .split(/\r?\n(?=\S)/)
    .map((block) => block.trim())
    .filter(Boolean);
  const nodes: OntologyNode[] = [];
  const relationships: OntologyRelationship[] = [];

  blocks.forEach((block) => {
    const lines = block.split(/\r?\n/);
    const name = lines[0]?.replace(/:$/, "").trim();
    if (!name) return;
    const fields = Object.fromEntries(
      lines.slice(1).map((line) => {
        const separator = line.indexOf(":");
        return [
          line.slice(0, separator).trim(),
          separator >= 0 ? line.slice(separator + 1).trim() : ""
        ];
      })
    );
    if ("from" in fields || "to" in fields) {
      relationships.push({
        type: name as OntologyRelationship["type"],
        from: (fields.from || null) as KnowledgeEntityType | null,
        to: (fields.to || null) as KnowledgeEntityType | null,
        description: fields.description || "Relationship ontology contract"
      });
    } else {
      nodes.push({
        type: name as KnowledgeEntityType,
        description: fields.description || null
      });
    }
  });

  return { nodes, relationships };
}

export function serializeOntology(
  nodes: OntologyNode[],
  relationships: OntologyRelationship[]
): string {
  const nodeBlocks = nodes.map((node) =>
    `${node.type}:\n  description: ${node.description ?? ""}`
  );
  const relationshipBlocks = relationships.map((relationship) =>
    [
      `${relationship.type}:`,
      `  from: ${relationship.from ?? ""}`,
      `  to: ${relationship.to ?? ""}`,
      relationship.description && relationship.description !== "Relationship ontology contract"
        ? `  description: ${relationship.description}`
        : null
    ].filter(Boolean).join("\n")
  );
  return [...nodeBlocks, ...relationshipBlocks].join("\n\n");
}

export function serializeSchema(
  nodes: OntologyNode[],
  relationships: OntologyRelationship[],
  currentSchema: string
): string {
  const replaceList = (content: string, section: string, values: string[]) => {
    const block = [`${section}:`, ...values.map((value) => `  - ${value}`)].join("\n");
    const pattern = new RegExp(`^${section}:\\s*\\n(?:[ \\t]+-[^\\n]+\\n?)*`, "m");
    return pattern.test(content) ? content.replace(pattern, `${block}\n`) : `${block}\n\n${content}`;
  };
  return replaceList(
    replaceList(currentSchema, "nodes", nodes.map((node) => node.type)),
    "relationships",
    relationships.map((relationship) => relationship.type)
  ).trim();
}

export function parseNodeTypeDefinitions(content: string): Record<string, NodeTypeDefinition> {
  const definitions: Record<string, NodeTypeDefinition> = {};
  let inSection = false;
  let current = "";
  let activeList: "requiredProperties" | "optionalProperties" | null = null;

  const parseList = (rawValue: string) => rawValue
    .replace(/^\[/, "")
    .replace(/\]$/, "")
    .split(",")
    .map((value) => value.trim().replace(/^['"]|['"]$/g, ""))
    .filter(Boolean);

  for (const line of content.split(/\r?\n/)) {
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
      definitions[current] = { abstract: false, extends: null, requiredProperties: [], optionalProperties: [] };
      continue;
    }
    if (!current) continue;

    const listItem = line.match(/^      -\s*(.+?)\s*$/);
    if (listItem && activeList) {
      definitions[current][activeList].push(
        listItem[1].trim().replace(/^['"]|['"]$/g, "")
      );
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

function typeLineage(type: string, definitions: Record<string, NodeTypeDefinition>): Set<string> {
  const lineage = new Set<string>();
  let current: string | null = type;
  while (current && !lineage.has(current)) {
    lineage.add(current);
    current = definitions[current]?.extends ?? null;
  }
  return lineage;
}

export function resolveNodeTypeProperties(
  type: string,
  definitions: Record<string, NodeTypeDefinition>
): Pick<NodeTypeDefinition, "requiredProperties" | "optionalProperties"> {
  const required = new Set<string>();
  const optional = new Set<string>();
  for (const current of typeLineage(type, definitions)) {
    definitions[current]?.requiredProperties.forEach((property) => required.add(property));
    definitions[current]?.optionalProperties.forEach((property) => optional.add(property));
  }
  required.forEach((property) => optional.delete(property));
  return {
    requiredProperties: [...required].sort(),
    optionalProperties: [...optional].sort()
  };
}

export function validateKnowledgeGraph(
  entities: KnowledgeEntity[],
  relationships: KnowledgeRelationship[] = [],
  nodes: OntologyNode[] = ontologyNodes,
  relationshipDefinitions: OntologyRelationship[] = ontologyRelationships,
  nodeTypeDefinitions: Record<string, NodeTypeDefinition> = {}
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const persistedEntities = entities.filter((entity) => entity.status !== "missing");

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

  entities
    .filter((entity) => entity.status === "missing")
    .forEach((entity) => {
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

  relationships
    .filter((relationship) => !relationship.source.trim())
    .forEach((relationship) => {
      issues.push({
        id: `relationship-source-${relationship.id}`,
        severity: "error",
        title: "Relationship thiếu nguồn",
        message: `${relationship.fromEntityId} → ${relationship.toEntityId} chưa có provenance.`,
        path: `relationships.csv.${relationship.id}.source`,
        target: "relationships"
      });
    });

  if (!persistedEntities.some((entity) => Object.keys(entity.properties).length > 0)) {
    issues.push({
      id: "properties-empty",
      severity: "warning",
      title: "Chưa có properties",
      message: "properties.csv đang rỗng; entity chưa có thuộc tính nghiệp vụ.",
      path: "properties.csv",
      target: "entities"
    });
  }

  persistedEntities.forEach((entity) => {
    const required = new Set<string>();
    typeLineage(entity.type, nodeTypeDefinitions).forEach((type) => {
      nodeTypeDefinitions[type]?.requiredProperties.forEach((property) => required.add(property));
    });
    const missing = [...required].filter((property) => !(property in entity.properties));
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

  const entityById = new Map(entities.map((entity) => [entity.id, entity]));
  relationships.forEach((relationship) => {
    const definition = relationshipDefinitions.find((item) => item.type === relationship.relationship);
    const fromEntity = entityById.get(relationship.fromEntityId);
    const toEntity = entityById.get(relationship.toEntityId);
    const matches = (actual: string, expected: string | null) => !expected || expected.split("|").some((type) => typeLineage(actual, nodeTypeDefinitions).has(type));
    if (definition && fromEntity && !matches(fromEntity.type, definition.from)) {
      issues.push({ id: `from-type-${relationship.id}`, severity: "error", title: "Sai type đầu cạnh", message: `${fromEntity.type} không phù hợp với ${definition.from}.`, path: `relationships.csv.${relationship.id}`, entityId: fromEntity.id, target: "relationships" });
    }
    if (definition && toEntity && !matches(toEntity.type, definition.to)) {
      issues.push({ id: `to-type-${relationship.id}`, severity: "error", title: "Sai type cuối cạnh", message: `${toEntity.type} không phù hợp với ${definition.to}.`, path: `relationships.csv.${relationship.id}`, entityId: toEntity.id, target: "relationships" });
    }
  });

  const nearDefinition = relationshipDefinitions.find((item) => item.type === "NEAR");
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

  nodes
    .filter((node) => !node.description)
    .forEach((node) => {
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
