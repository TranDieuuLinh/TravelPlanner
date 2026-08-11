"use client";

import { useEffect, useMemo, useState } from "react";
import {
  listKGAutoAttachRules,
  upsertKGAutoAttachRule,
  type KGAutoAttachRule,
  listKGAutoAttachAliases,
  upsertKGAutoAttachAlias,
  type KGAutoAttachAlias,
} from "../../../features/knowledge-graph/lib";

type Rule = {
  id: string;
  name: string;
  group: string;
  entityTypes: string[];
  keywords: string[];
  exactNames: string[];
  exclusions: string[];
  duration: string;
  windows: string[];
  overrides: number;
};

const SEED: Rule[] = [
  { id: "style_breakfast", name: "Ăn sáng", group: "meal", entityTypes: ["FoodItem", "Restaurant", "DrinkDessert"], keywords: ["phở", "bánh mì", "xôi", "cháo", "bún", "cà phê"], exactNames: [], exclusions: ["cơm văn phòng"], duration: "PT45M", windows: ["06:00–10:00"], overrides: 0 },
  { id: "style_lunch", name: "Ăn trưa", group: "meal", entityTypes: ["FoodItem", "Restaurant", "DrinkDessert"], keywords: ["phở", "cơm", "bún", "mì", "lẩu", "buffet", "món Việt"], exactNames: [], exclusions: ["cơm văn phòng"], duration: "PT45M", windows: ["11:00–13:00"], overrides: 0 },
  { id: "style_dinner", name: "Ăn tối", group: "meal", entityTypes: ["FoodItem", "Restaurant", "DrinkDessert"], keywords: ["phở", "cơm", "bún", "lẩu", "nướng", "hải sản", "pizza"], exactNames: [], exclusions: ["cơm văn phòng"], duration: "PT60M", windows: ["18:00–20:00"], overrides: 0 },
  { id: "style_visit_pass_by", name: "Ghé qua", group: "sightseeing", entityTypes: ["TravelPlace"], keywords: ["đền", "đình", "chùa", "tháp", "cầu", "quảng trường", "hồ", "chợ"], exactNames: ["tháp rùa", "chùa một cột", "đền ngọc sơn"], exclusions: [], duration: "PT30M", windows: ["08:00–10:00", "14:00–17:00"], overrides: 0 },
  { id: "style_sightseeing", name: "Tham quan", group: "sightseeing", entityTypes: ["TravelPlace"], keywords: ["lăng", "bảo tàng", "di tích", "cung điện", "vườn quốc gia", "hang động"], exactNames: ["lăng bác", "hoàng thành thăng long", "nhà tù hỏa lò"], exclusions: [], duration: "PT120M", windows: ["08:00–10:00", "14:00–17:00"], overrides: 0 },
  { id: "style_drinking", name: "Ăn nhậu", group: "nightlife", entityTypes: ["FoodItem", "DrinkItem", "Restaurant", "DrinkDessert"], keywords: ["bia", "beer", "rượu", "lẩu", "nướng", "hải sản", "đồ nhậu"], exactNames: [], exclusions: [], duration: "PT180M", windows: ["18:00–22:00"], overrides: 2 },
  { id: "style_play_entertainment", name: "Vui chơi & Giải trí", group: "entertainment", entityTypes: ["TravelPlace", "ActivityItem"], keywords: ["karaoke", "bida", "bowling", "bắn cung", "paintball", "karting", "thủy cung"], exactNames: [], exclusions: [], duration: "PT120M", windows: ["14:00–17:00", "20:00–23:00"], overrides: 4 },
  { id: "style_nightlife", name: "Cuộc sống về đêm", group: "nightlife", entityTypes: ["TravelPlace", "DrinkItem", "DrinkDessert", "ActivityItem"], keywords: ["bar", "pub", "rooftop", "club", "cocktail", "chợ đêm", "phố đi bộ"], exactNames: ["phố bia tạ hiện", "chợ đêm phố cổ"], exclusions: [], duration: "PT120M", windows: ["20:00–23:59", "00:00–03:00"], overrides: 3 },
  { id: "style_outdoor_experience", name: "Ngoài trời & Trải nghiệm", group: "outdoor", entityTypes: ["TravelPlace", "ActivityItem"], keywords: ["hồ", "biển", "núi", "trekking", "cắm trại", "kayak", "đạp xe"], exactNames: ["hồ gươm", "hồ tây"], exclusions: [], duration: "PT60M", windows: ["06:00–10:00", "15:00–22:00"], overrides: 5 },
  { id: "style_food_relaxation", name: "Ẩm thực & Thư giãn", group: "food_relaxation", entityTypes: ["FoodItem", "DrinkItem", "DrinkDessert", "Restaurant"], keywords: ["cà phê", "trà sữa", "bánh ngọt", "kem", "chè", "brunch"], exactNames: [], exclusions: [], duration: "PT60M", windows: ["14:00–17:00", "20:00–22:00"], overrides: 0 },
  { id: "style_shopping_discovery", name: "Mua sắm & Khám phá", group: "shopping", entityTypes: ["TravelPlace", "ProductItem"], keywords: ["chợ", "chợ nổi", "trung tâm thương mại", "đặc sản", "gốm", "lụa", "đồ lưu niệm"], exactNames: [], exclusions: [], duration: "PT90M", windows: ["09:00–12:00", "16:00–22:00"], overrides: 0 },
  { id: "style_relaxation_self_care", name: "Thư giãn & Chăm sóc bản thân", group: "wellness", entityTypes: ["Accommodation", "TravelPlace", "ActivityItem"], keywords: ["spa", "massage", "gội đầu dưỡng sinh", "xông hơi", "yoga", "thiền", "nail"], exactNames: [], exclusions: [], duration: "PT90M", windows: ["09:00–12:00", "14:00–22:00"], overrides: 0 }
];

const ALIAS_SEED: KGAutoAttachAlias[] = [
  { keyword: "chợ", aliases: ["market"], source: "attach_auto.yml" },
  { keyword: "chợ đêm", aliases: ["night market"], source: "attach_auto.yml" },
  { keyword: "phố đi bộ", aliases: ["walking street", "pedestrian street"], source: "attach_auto.yml" },
  { keyword: "phố cổ", aliases: ["old quarter", "old town", "ancient town"], source: "attach_auto.yml" },
  { keyword: "phở", aliases: ["pho", "vietnamese noodle soup"], source: "attach_auto.yml" },
  { keyword: "bánh mì", aliases: ["banh mi", "vietnamese sandwich"], source: "attach_auto.yml" },
  { keyword: "xôi", aliases: ["sticky rice"], source: "attach_auto.yml" },
  { keyword: "cháo", aliases: ["rice porridge", "congee"], source: "attach_auto.yml" },
  { keyword: "bún", aliases: ["rice vermicelli"], source: "attach_auto.yml" },
  { keyword: "bún chả", aliases: ["bun cha", "grilled pork with vermicelli"], source: "attach_auto.yml" },
  { keyword: "bún bò", aliases: ["bun bo", "beef vermicelli soup"], source: "attach_auto.yml" },
  { keyword: "bún riêu", aliases: ["bun rieu", "crab noodle soup"], source: "attach_auto.yml" },
  { keyword: "bánh cuốn", aliases: ["steamed rice rolls"], source: "attach_auto.yml" },
  { keyword: "cơm tấm", aliases: ["broken rice"], source: "attach_auto.yml" },
  { keyword: "cơm niêu", aliases: ["clay pot rice"], source: "attach_auto.yml" },
];

const normalize = (value: string) => value.toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const lines = (value: string) => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
const groupLabel = (value: string) => value.replaceAll("_", " ");
const parseAliases = (value: string): KGAutoAttachAlias[] => value.split("\n").map((line) => {
  const [keyword, aliasText = ""] = line.split(":");
  return { keyword: keyword.trim(), aliases: aliasText.split(",").map((item) => item.trim()).filter(Boolean), source: "attach_auto.yml" };
}).filter((item) => item.keyword);

function fromApiRule(rule: KGAutoAttachRule): Rule {
  return {
    id: rule.ruleId,
    name: rule.name,
    group: rule.styleGroup,
    entityTypes: rule.entityTypes,
    keywords: rule.keywords,
    exactNames: rule.exactNames,
    exclusions: rule.excludeKeywords,
    duration: rule.timeDuration,
    windows: rule.timeWindows.map((window) => `${window.start}–${window.end}`),
    overrides: rule.overrideCount,
  };
}

function toApiRule(rule: Rule): KGAutoAttachRule {
  return {
    ruleId: rule.id,
    name: rule.name,
    styleGroup: rule.group,
    entityTypes: rule.entityTypes,
    keywords: rule.keywords,
    exactNames: rule.exactNames,
    excludeKeywords: rule.exclusions,
    timeDuration: rule.duration,
    timeWindows: rule.windows.map((value) => {
      const [start, end] = value.split("–");
      return { start: start?.trim() ?? "", end: end?.trim() ?? "" };
    }),
    overrideCount: rule.overrides,
    status: "pending",
    source: "attach_auto.yml",
  };
}

function exportDraft(rules: Rule[]) {
  const output = ["version: \"0.1.0\"", "relationship: Has_Style", "", "styles:"];
  rules.forEach((rule) => {
    output.push(`  - id: ${rule.id}`, `    name: ${JSON.stringify(rule.name)}`, `    style_group: ${rule.group}`, `    entity_types: [${rule.entityTypes.join(", ")}]`, "    keywords:");
    rule.keywords.forEach((keyword) => output.push(`      - ${JSON.stringify(keyword)}`));
    if (rule.exactNames.length) { output.push("    exact_names:"); rule.exactNames.forEach((name) => output.push(`      - ${JSON.stringify(name)}`)); }
    if (rule.exclusions.length) { output.push("    exclude_keywords:"); rule.exclusions.forEach((name) => output.push(`      - ${JSON.stringify(name)}`)); }
    output.push(`    time_duration: ${rule.duration}`, "    time_windows:");
    rule.windows.forEach((window) => { const [start, end] = window.split("–"); output.push(`      - {start: "${start}", end: "${end}"}`); });
    output.push("");
  });
  output.push("rule_defaults:", "  match_mode: normalized_name_or_alias", "  case_sensitive: false", "  accent_sensitive: false", "  keyword_match: contains", "  auto_attach_status: pending");
  return output.join("\n");
}

export default function AutoAttachPage() {
  const [rules, setRules] = useState(SEED);
  const [selectedId, setSelectedId] = useState(SEED[0].id);
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState("Bắn cung trong nhà");
  const [draftSaved, setDraftSaved] = useState(false);
  const [backendState, setBackendState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [saving, setSaving] = useState(false);
  const [backendError, setBackendError] = useState("");
  const [aliases, setAliases] = useState<KGAutoAttachAlias[]>(ALIAS_SEED);
  const selected = rules.find((rule) => rule.id === selectedId) ?? rules[0];
  const filtered = rules.filter((rule) => `${rule.name} ${rule.group} ${rule.keywords.join(" ")}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const matches = useMemo(() => {
    const value = normalize(preview);
    return rules.filter((rule) => !rule.exclusions.some((item) => value.includes(normalize(item))) && (rule.keywords.some((item) => value.includes(normalize(item))) || rule.exactNames.some((item) => value === normalize(item))));
  }, [preview, rules]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listKGAutoAttachRules(), listKGAutoAttachAliases()]).then(([response, aliasResponse]) => {
      if (cancelled) return;
      if (aliasResponse.items.length) setAliases(aliasResponse.items);
      if (!response.items.length) {
        setBackendState("empty");
        return;
      }
      const loaded = response.items.map(fromApiRule);
      setRules(loaded);
      setSelectedId(loaded[0].id);
      setBackendState("ready");
    }).catch((error: unknown) => {
      if (cancelled) return;
      setBackendState("error");
      setBackendError(error instanceof Error ? error.message : "Backend unavailable");
    });
    return () => { cancelled = true; };
  }, []);

  function update(patch: Partial<Rule>) { setDraftSaved(false); setRules((current) => current.map((rule) => rule.id === selected.id ? { ...rule, ...patch } : rule)); }
  async function saveSelected() {
    setSaving(true);
    setBackendError("");
    try {
      await upsertKGAutoAttachRule(toApiRule(selected));
      setBackendState("ready");
      setDraftSaved(true);
    } catch (error: unknown) {
      setBackendError(error instanceof Error ? error.message : "Không thể lưu rule");
    } finally {
      setSaving(false);
    }
  }
  async function saveAll() {
    setSaving(true);
    setBackendError("");
    try {
      await Promise.all([
        ...rules.map((rule) => upsertKGAutoAttachRule(toApiRule(rule))),
        ...aliases.map((alias) => upsertKGAutoAttachAlias(alias)),
      ]);
      setBackendState("ready");
      setDraftSaved(true);
    } catch (error: unknown) {
      setBackendError(error instanceof Error ? error.message : "Không thể lưu rules");
    } finally {
      setSaving(false);
    }
  }
  function addRule() { const id = `style_new_${rules.length + 1}`; setRules((current) => [...current, { id, name: "Style mới", group: "experience", entityTypes: ["TravelPlace"], keywords: [], exactNames: [], exclusions: [], duration: "PT60M", windows: ["08:00–18:00"], overrides: 0 }]); setSelectedId(id); setDraftSaved(false); }
  function download() { const url = URL.createObjectURL(new Blob([exportDraft(rules)], { type: "text/yaml;charset=utf-8" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "attach_auto.draft.yml"; anchor.click(); URL.revokeObjectURL(url); }

  return <div className="autoAttachPage">
    <header className="autoAttachHero"><div><div className="kgEyebrow">KNOWLEDGE GRAPH / RULE STUDIO</div><h1>Auto Attach <span>Style</span></h1><p>Quản lý keyword, alias, exclusion và giờ riêng để nối entity vào Style qua Has_Style.</p></div><div className="autoAttachHeroActions"><span className="autoAttachDraftBadge"><i /> Backend rules</span><button type="button" className="kgPrimaryButton" onClick={saveAll} disabled={saving}>{saving ? "Saving…" : "Save all"}</button><button type="button" className="kgPrimaryButton" onClick={download}>Export YAML</button></div></header>
    <div className={`autoAttachNotice ${backendState === "error" ? "error" : ""}`}><span>◎</span><div><b>{backendState === "ready" ? "Rules đã kết nối backend" : backendState === "empty" ? "Backend chưa có rule" : backendState === "error" ? "Không kết nối được backend" : "Đang tải rules từ backend"}</b><p>{backendError || "Rule được lưu trong knowledge_auto_attach_rules. Auto-attach mặc định tạo candidate ở trạng thái pending."}</p></div></div>
    <section className="autoAttachMetrics"><article><small>STYLE RULES</small><strong>{rules.length}</strong><span>taxonomy đang quản lý</span></article><article><small>KEYWORDS</small><strong>{rules.reduce((sum, rule) => sum + rule.keywords.length, 0)}</strong><span>match contains + alias</span></article><article><small>OVERRIDES</small><strong>{rules.reduce((sum, rule) => sum + rule.overrides, 0)}</strong><span>giờ riêng cho entity</span></article><article><small>RELATIONSHIP</small><strong>Has_Style</strong><span>candidate → review</span></article></section>
    <section className="autoAttachWorkspace"><aside className="autoAttachSidebar"><div className="autoAttachSidebarHeader"><div><small>STYLE CATALOG</small><b>{filtered.length} rules</b></div><button type="button" onClick={addRule}>＋ Add</button></div><label className="autoAttachSearch"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm style hoặc keyword…" /></label><div className="autoAttachRuleList">{filtered.map((rule) => <button type="button" key={rule.id} className={`autoAttachRuleItem ${rule.id === selected.id ? "active" : ""}`} onClick={() => setSelectedId(rule.id)}><span className="autoAttachRuleIcon">{rule.name.slice(0, 1)}</span><span><b>{rule.name}</b><small>{groupLabel(rule.group)} · {rule.keywords.length} keywords</small></span><i>›</i></button>)}</div></aside>
      <main className="autoAttachEditor"><div className="autoAttachEditorHeader"><div><small>EDITING RULE</small><h2>{selected.name}</h2><code>{selected.id}</code></div><span className="autoAttachPending">PENDING REVIEW</span></div><div className="autoAttachFormGrid"><label><span>Display name</span><input value={selected.name} onChange={(event) => update({ name: event.target.value })} /></label><label><span>Style group</span><input value={selected.group} onChange={(event) => update({ group: event.target.value })} /></label><label className="autoAttachWide"><span>Allowed entity types</span><input value={selected.entityTypes.join(", ")} onChange={(event) => update({ entityTypes: lines(event.target.value) })} /></label></div><div className="autoAttachSection"><div className="autoAttachSectionTitle"><div><b>Keyword matcher</b><span>Match tên đã normalize, không phân biệt dấu.</span></div><em>CONTAINS</em></div><textarea value={selected.keywords.join("\n")} onChange={(event) => update({ keywords: lines(event.target.value) })} placeholder="mỗi keyword một dòng" /></div><div className="autoAttachDualGrid"><div className="autoAttachSection"><div className="autoAttachSectionTitle"><div><b>Exact names</b><span>Dành cho địa danh đặc biệt.</span></div></div><textarea value={selected.exactNames.join("\n")} onChange={(event) => update({ exactNames: lines(event.target.value) })} placeholder="lăng bác" /></div><div className="autoAttachSection"><div className="autoAttachSectionTitle"><div><b>Exclusions</b><span>Loại trước khi match keyword gốc.</span></div></div><textarea value={selected.exclusions.join("\n")} onChange={(event) => update({ exclusions: lines(event.target.value) })} placeholder="cơm văn phòng" /></div></div><div className="autoAttachTimingGrid"><label><span>Default duration</span><input value={selected.duration} onChange={(event) => update({ duration: event.target.value })} /></label><label><span>Default windows</span><input value={selected.windows.join(", ")} onChange={(event) => update({ windows: lines(event.target.value) })} /></label><div className="autoAttachOverrideStat"><small>ENTITY OVERRIDES</small><strong>{selected.overrides}</strong><span>hoạt động có giờ riêng</span></div></div><div className="autoAttachEditorFooter"><span>{draftSaved ? "Rule đã lưu vào backend" : "Có thay đổi chưa lưu"}</span><button type="button" className="kgPrimaryButton" onClick={saveSelected} disabled={saving}>{saving ? "Saving…" : "Save to backend"}</button></div></main></section>
    <section className="autoAttachPreview"><div className="autoAttachPreviewHeader"><div><small>LIVE MATCH PREVIEW</small><h2>Thử một tên entity</h2></div><label><span>Entity name</span><input value={preview} onChange={(event) => setPreview(event.target.value)} /></label></div><div className="autoAttachPreviewResult"><span className="autoAttachPreviewEntity">{preview || "Chưa nhập tên"}</span><b>→</b>{matches.length ? matches.map((rule) => <span className="autoAttachMatchChip" key={rule.id}>{rule.name}<small>Has_Style</small></span>) : <span className="autoAttachNoMatch">Chưa có Style match</span>}</div><p>Preview mô phỏng keyword contains và exclusions; exact match/override sẽ được engine áp dụng ở bước sau.</p></section>
    <section className="autoAttachAliasPanel"><div className="autoAttachSectionTitle"><div><small>KEYWORD ALIASES</small><h2>Vietnamese → English</h2><span>Mỗi dòng một keyword: alias1, alias2. Các alias được lưu trong backend riêng.</span></div><strong>{aliases.length} aliases</strong></div><textarea value={aliases.map((alias) => `${alias.keyword}: ${alias.aliases.join(", ")}`).join("\n")} onChange={(event) => setAliases(parseAliases(event.target.value))} /></section>
  </div>;
}
