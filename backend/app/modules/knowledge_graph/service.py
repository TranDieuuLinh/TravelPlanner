from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from uuid import uuid4

import yaml

from app.integrations.llm.base import LLMClient
from app.modules.knowledge_graph.dataset import KnowledgeGraphDataset
from app.modules.knowledge_graph.repositories import (
    GraphImportRepository,
    KnowledgeGraphRepository,
)
from app.modules.knowledge_graph.schema import (
    ExtractionOutput,
    GraphImportCreate,
    ProposedEdgeUpdate,
    ProposedNodeUpdate,
)
from app.modules.knowledge_graph.text import normalize_knowledge_text
from app.shared.errors import AppError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized(value: str) -> str:
    return normalize_knowledge_text(value)


class KnowledgeGraphImportService:
    def __init__(
        self,
        import_repository: GraphImportRepository,
        kg_repository: KnowledgeGraphRepository,
        dataset: KnowledgeGraphDataset,
        llm: LLMClient,
    ) -> None:
        self.import_repository = import_repository
        self.kg_repository = kg_repository
        self.dataset = dataset
        self.llm = llm

    async def create(self, payload: GraphImportCreate, *, user_id: int) -> dict:
        import_id = uuid4().hex
        schema, ontology = self.dataset.raw_contract()
        job = {
            "id": import_id,
            "source_label": payload.source_label,
            "source_url": payload.source_url,
            "source_content": payload.content,
            "status": "extracting",
            "schema_version": self._content_version(schema),
            "ontology_version": self._content_version(ontology),
            "dataset_hash": self.dataset.hash(),
            "warnings": [],
            "nodes": [],
            "edges": [],
            "created_by": user_id,
            "created_at": _now(),
            "applied_at": None,
            "error_message": None,
        }
        self.import_repository.save(job)
        try:
            extracted = await self._extract(payload, schema=schema, ontology=ontology)
            job["warnings"] = extracted.warnings
            job["nodes"] = []
            for node in extracted.nodes:
                node_type = node.type
                type_prefix = self.dataset.entity_type_prefix(node_type)
                suggested_id = node.entity_id if node.entity_id else self.dataset.next_entity_id(type_prefix)
                job["nodes"].append({
                    **node.model_dump(),
                    "entity_id": suggested_id,
                    "match_status": "new",
                    "match_candidates": [],
                    "selected_entity_id": None,
                    "decision": "pending",
                    "validation_issues": [],
                    "required_properties": sorted(self.dataset.required_properties(node_type)),
                    "optional_properties": sorted(self.dataset.optional_properties(node_type)),
                })
            job["edges"] = [
                {
                    **edge.model_dump(),
                    "match_status": "new",
                    "decision": "pending",
                    "validation_issues": [],
                }
                for edge in extracted.edges
            ]
            self._rematch(job)
            job["status"] = "needs_review"
            self._refresh_counts(job)
            return self.import_repository.save(job)
        except Exception as exc:
            job["status"] = "failed"
            job["error_message"] = str(exc)[:500]
            self.import_repository.save(job)
            raise AppError(
                502,
                "KNOWLEDGE_GRAPH_EXTRACTION_FAILED",
                "AI không thể tạo graph proposal hợp lệ.",
            ) from exc

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        return self.import_repository.list(
            limit=limit, offset=offset, status=status, search=search
        )

    def count(self) -> int:
        return self.import_repository.count()

    def get(self, import_id: str) -> dict:
        job = self.import_repository.get(import_id)
        if job is None:
            raise AppError(404, "GRAPH_IMPORT_NOT_FOUND", "Không tìm thấy AI import.")
        self._refresh_counts(job)
        return job

    def get_meta(self, import_id: str) -> dict:
        job = self.get(import_id)
        return self._meta_dict(job)

    def list_nodes(self, import_id: str, *, limit: int, offset: int) -> tuple[list[dict], int]:
        job = self.get(import_id)
        items = job.get("nodes", [])
        total = len(items)
        sliced = items[offset:offset + limit]
        return sliced, total

    def list_edges(self, import_id: str, *, limit: int, offset: int) -> tuple[list[dict], int]:
        job = self.get(import_id)
        items = job.get("edges", [])
        total = len(items)
        sliced = items[offset:offset + limit]
        return sliced, total

    @staticmethod
    def _summary_dict(job: dict) -> dict:
        nodes = job.get("nodes", []) or []
        edges = job.get("edges", []) or []
        return {
            "id": job.get("id", ""),
            "source_label": job.get("source_label", ""),
            "source_url": job.get("source_url"),
            "status": job.get("status", "failed"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "issue_count": sum(
                len(item.get("validation_issues", []))
                for item in [*nodes, *edges]
                if isinstance(item, dict)
            ),
            "created_at": job.get("created_at", ""),
            "applied_at": job.get("applied_at"),
            "error_message": job.get("error_message"),
        }

    @classmethod
    def _meta_dict(cls, job: dict) -> dict:
        return {
            **cls._summary_dict(job),
            "source_content": job.get("source_content", ""),
            "schema_version": job.get("schema_version", ""),
            "ontology_version": job.get("ontology_version", ""),
            "dataset_hash": job.get("dataset_hash", ""),
            "warnings": job.get("warnings", []) or [],
        }

    def update_node(self, import_id: str, temp_id: str, payload: ProposedNodeUpdate) -> dict:
        job = self._editable(import_id)
        node = next((item for item in job["nodes"] if item.get("temp_id") == temp_id), None)
        if node is None:
            raise AppError(404, "PROPOSED_NODE_NOT_FOUND", "Không tìm thấy node proposal.")
        node.update(payload.model_dump())
        self._rematch(job)
        self._refresh_counts(job)
        return self.import_repository.save(job)

    def update_edge(self, import_id: str, temp_id: str, payload: ProposedEdgeUpdate) -> dict:
        job = self._editable(import_id)
        edge = next((item for item in job["edges"] if item.get("temp_id") == temp_id), None)
        if edge is None:
            raise AppError(404, "PROPOSED_EDGE_NOT_FOUND", "Không tìm thấy edge proposal.")
        edge.update(payload.model_dump())
        self._rematch(job)
        self._refresh_counts(job)
        return self.import_repository.save(job)

    def revalidate(self, import_id: str) -> dict:
        job = self._editable(import_id)
        schema, ontology = self.dataset.raw_contract()
        job["dataset_hash"] = self.dataset.hash()
        job["schema_version"] = self._content_version(schema)
        job["ontology_version"] = self._content_version(ontology)
        for item in [*job.get("nodes", []), *job.get("edges", [])]:
            item["decision"] = "pending"
        self._rematch(job)
        self._refresh_counts(job)
        return self.import_repository.save(job)

    def delete_node(self, import_id: str, temp_id: str) -> dict:
        job = self._editable(import_id)
        node = next((item for item in job["nodes"] if item["temp_id"] == temp_id), None)
        if node is None:
            raise AppError(404, "PROPOSED_NODE_NOT_FOUND", "Không tìm thấy node proposal.")
        job["nodes"] = [item for item in job["nodes"] if item["temp_id"] != temp_id]
        job["edges"] = [
            item for item in job["edges"]
            if item["from_ref"] != temp_id and item["to_ref"] != temp_id
        ]
        self._refresh_counts(job)
        return self.import_repository.save(job)

    def delete_edge(self, import_id: str, temp_id: str) -> dict:
        job = self._editable(import_id)
        edge = next((item for item in job["edges"] if item["temp_id"] == temp_id), None)
        if edge is None:
            raise AppError(404, "PROPOSED_EDGE_NOT_FOUND", "Không tìm thấy edge proposal.")
        job["edges"] = [item for item in job["edges"] if item["temp_id"] != temp_id]
        self._refresh_counts(job)
        return self.import_repository.save(job)

    def delete_import(self, import_id: str) -> str:
        existing = self.import_repository.get(import_id)
        if existing is None:
            raise AppError(404, "IMPORT_NOT_FOUND", "Không tìm thấy graph import job.")
        self.import_repository.delete(import_id)
        return import_id

    def apply(self, import_id: str) -> dict:
        job = self._editable(import_id)
        existing_entity_ids = {
            row.get("id", "") for row in self.dataset.entities()
        }
        node_mapping: dict[str, str] = {}
        approved_nodes = []
        for node in job["nodes"]:
            decision = node["decision"]
            if decision.startswith("approve_") and node.get("validation_issues"):
                raise AppError(422, "NODE_VALIDATION_FAILED", "Node đã duyệt vẫn còn validation issue.")
            if decision == "approve_existing":
                if not node.get("selected_entity_id"):
                    raise AppError(422, "MATCH_REQUIRED", "Node dùng entity hiện có nhưng chưa chọn entity.")
                if node["selected_entity_id"] not in existing_entity_ids:
                    raise AppError(422, "MATCH_NOT_FOUND", "Entity được chọn không còn tồn tại.")
                node_mapping[node["temp_id"]] = node["selected_entity_id"]
                approved_nodes.append({
                    **node,
                    "property_source": job.get("source_url") or job["source_label"],
                })
            elif decision == "approve_create":
                if node["entity_id"] in existing_entity_ids:
                    raise AppError(409, "ENTITY_ID_EXISTS", "Entity ID tạo mới đã tồn tại.")
                node_mapping[node["temp_id"]] = node["entity_id"]
                approved_nodes.append({
                    **node,
                    "property_source": job.get("source_url") or job["source_label"],
                })

        approved_edges = []
        for edge in job["edges"]:
            if edge["decision"] not in {"approve_create", "approve_existing"}:
                continue
            if edge.get("validation_issues"):
                raise AppError(422, "EDGE_VALIDATION_FAILED", "Edge đã duyệt vẫn còn validation issue.")
            from_id = node_mapping.get(edge["from_ref"])
            to_id = node_mapping.get(edge["to_ref"])
            if not from_id or not to_id:
                raise AppError(
                    422,
                    "EDGE_ENDPOINT_NOT_APPROVED",
                    "Không thể apply edge khi node nguồn hoặc đích chưa được duyệt.",
                )
            approved_edges.append({**edge, "from_id": from_id, "to_id": to_id})

        if not approved_nodes and not approved_edges:
            raise AppError(422, "NOTHING_APPROVED", "Chưa có node hoặc edge nào được duyệt.")
        try:
            new_hash = self.dataset.apply(
                nodes=approved_nodes,
                edges=approved_edges,
                expected_hash=job["dataset_hash"],
            )
        except ValueError as exc:
            if str(exc) == "DATASET_VERSION_CONFLICT":
                raise AppError(
                    409,
                    "DATASET_VERSION_CONFLICT",
                    "Knowledge graph đã thay đổi. Hãy tạo hoặc revalidate proposal mới.",
                ) from exc
            raise
        job["status"] = "applied"
        job["applied_at"] = _now()
        job["applied_dataset_hash"] = new_hash
        self._refresh_counts(job)
        return self.import_repository.save(job)

    async def _extract(
        self,
        payload: GraphImportCreate,
        *,
        schema: str,
        ontology: str,
    ) -> ExtractionOutput:
        property_definitions = self._property_definitions()

        system_prompt = (
            "Bạn là chuyên gia quản tuyển knowledge graph cho ứng dụng lập kế hoạch du lịch Việt Nam. "
            "Nhiệm vụ của bạn là trích xuất entity và relationship có cấu trúc từ nội dung nguồn.\n\n"
            "## QUY TẮC TỐI QUAN TRỌNG\n"
            "1. CHỈ dùng node type và relationship type được định nghĩa trong schema/ontology\n"
            "2. KHÔNG BAO GIỜ bịa sự thật không có trong nội dung nguồn\n"
            "3. Mọi node và edge PHẢI có trích dẫn bằng chứng nguyên văn từ nguồn\n"
            "4. Với địa điểm địa lý, đồng thời trích xuất tọa độ vĩ/độ nếu nguồn có cung cấp\n\n"
            "## HƯỚNG DẪN TRÍCH XUẤT\n"
            "- Xem schema và ontology được cung cấp trong user payload là contract duy nhất cho request hiện tại; không dùng danh sách type ghi nhớ từ dataset khác\n"
            "- Chỉ trích xuất node type concrete nằm trong schema.nodes. Mọi type trong schema.abstract_nodes chỉ phục vụ inheritance và không bao giờ được trả là type của node proposal\n"
            "- Dùng schema.node_type_definitions và ontology description để phân loại entity; không suy type chỉ từ tên hoặc category tự do\n"
            "- Chỉ trích xuất relationship nằm trong schema.relationships và tuân thủ chính xác from/to contract trong ontology; không tạo quan hệ chỉ vì hai entity cùng xuất hiện\n"
            "- Khi ontology mô tả một relationship cần evidence/source hoặc recommendations, chỉ tạo edge khi nguồn hỗ trợ trực tiếp và giữ đúng shape được yêu cầu\n"
            "- Chỉ trích xuất alias tiếng Việt/tiếng Anh thực sự xuất hiện trong nguồn; không dịch hoặc tạo đủ hai ngôn ngữ. Alias generated/verified được xử lý bởi pipeline knowledge_aliases riêng\n"
            "- Chỉ dùng property key có trong propertyDefinitions được cung cấp; không tạo key runtime nằm ngoài schema import\n"
            "- Tuân thủ required_properties và optional_properties theo toàn bộ type lineage trong schema.node_type_definitions. Nếu nguồn thiếu property bắt buộc, không bịa giá trị chỉ để làm proposal hợp lệ\n"
            "- Trích xuất hướng dẫn nổi bật hoặc nhất định nên thử của node vào property mảng JSON special_experience\n"
            "- Trích xuất recommendation và mẹo theo ngữ cảnh vào edge recommendation\n"
            "- Confidence phải phản ánh mức độ chắc chắn dựa trên chất lượng bằng chứng\n\n"
            "## KIỂU PROPERTY\n"
            "- string: văn bản thuần\n"
            "- number: giá trị số (int hoặc float)\n"
            "- boolean: true/false\n"
            "- json_array: mảng chuỗi hoặc object, mã hóa dưới dạng chuỗi JSON\n"
            "- json_object: object mã hóa dưới dạng chuỗi JSON\n\n"
            "Output chỉ là import proposal chờ validation/review, không phải tuyên bố entity đã được ghi vào graph canonical.\n"
            "CHỈ trả về JSON hợp lệ khớp response schema."
        )

        user_payload = json.dumps(
            {
                "schema": schema,
                "ontology": ontology,
                "propertyDefinitions": property_definitions,
                "responseContract": ExtractionOutput.model_json_schema(by_alias=True),
                "source": {
                    "label": payload.source_label,
                    "url": payload.source_url,
                    "content": payload.content,
                },
                "idPolicy": "Use stable lowercase snake_case suggestions; application code owns final identity.",
            },
            ensure_ascii=False,
        )
        raw = await self.llm.generate_json(system_prompt, user_payload)
        return ExtractionOutput.model_validate_json(raw)

    def _property_definitions(self) -> dict[str, str]:
        """Build property definitions from schema for LLM reference."""
        content = (self.dataset.directory / "schema.yaml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(content) or {}
        return parsed.get("property_definitions", {})

    def _rematch(self, job: dict) -> None:
        entities = self.dataset.entities()
        aliases = self.dataset.aliases()
        allowed_nodes = self.dataset.allowed_nodes()
        allowed_relationships = self.dataset.allowed_relationships()
        contracts = self.dataset.relationship_contracts()
        required_by_type: dict[str, set[str]] = {}
        optional_by_type: dict[str, set[str]] = {}
        type_match_cache: dict[tuple[str, tuple[str, ...]], bool] = {}

        def required(node_type: str) -> set[str]:
            if node_type not in required_by_type:
                required_by_type[node_type] = self.dataset.required_properties(node_type)
            return required_by_type[node_type]

        def optional(node_type: str) -> set[str]:
            if node_type not in optional_by_type:
                optional_by_type[node_type] = self.dataset.optional_properties(node_type)
            return optional_by_type[node_type]

        def type_matches(node_type: str, expected: set[str]) -> bool:
            key = (node_type, tuple(sorted(expected)))
            if key not in type_match_cache:
                type_match_cache[key] = self.dataset.type_matches(node_type, expected)
            return type_match_cache[key]
        alias_by_entity: dict[str, list[str]] = {}
        for alias in aliases:
            alias_by_entity.setdefault(alias.get("entity_id", ""), []).append(alias.get("alias", ""))

        for node in job["nodes"]:
            candidates = []
            proposed_name = _normalized(node["canonical_name"])
            for entity in entities:
                rules: list[str] = []
                score = 0
                existing_name = _normalized(entity.get("name", ""))
                alias_names = {_normalized(value) for value in alias_by_entity.get(entity.get("id", ""), [])}
                if proposed_name and proposed_name == existing_name:
                    rules.append("name_exact")
                    score = 95
                elif proposed_name and proposed_name in alias_names:
                    rules.append("alias_exact")
                    score = max(score, 92)
                if proposed_name and existing_name and score < 95:
                    similarity = SequenceMatcher(None, proposed_name, existing_name).ratio()
                    if similarity >= 0.78:
                        rules.append(f"name_similarity:{similarity:.2f}")
                        score = max(score, round(similarity * 85))
                if score:
                    candidates.append({
                        "entity_id": entity.get("id", ""),
                        "canonical_name": entity.get("name", ""),
                        "type": entity.get("type", ""),
                        "score": score,
                        "matched_rules": rules,
                    })
            candidates.sort(key=lambda item: item["score"], reverse=True)
            if candidates and candidates[0]["score"] >= 95:
                match_status = "existing"
            elif candidates and candidates[0]["score"] >= 65:
                match_status = "possible_duplicate"
            else:
                match_status = "new"
            node["match_status"] = match_status
            node["match_candidates"] = candidates[:5]
            if match_status == "existing" and not node.get("selected_entity_id"):
                node["selected_entity_id"] = candidates[0]["entity_id"]
            node["validation_issues"] = []
            if node["type"] not in allowed_nodes:
                node["validation_issues"].append("node_type_not_in_schema")
            missing_properties = required(node["type"]) - set(node.get("properties", {}))
            node["validation_issues"].extend(
                f"required_property_missing:{name}" for name in sorted(missing_properties)
            )
            node["required_properties"] = sorted(required(node["type"]))
            node["optional_properties"] = sorted(optional(node["type"]))
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", node["entity_id"]):
                node["validation_issues"].append("invalid_entity_id")

        node_by_ref = {node["temp_id"]: node for node in job["nodes"]}
        current_edges = {
            (row.get("from_entity_id"), row.get("relationship"), row.get("to_entity_id"))
            for row in self.dataset.relationships()
        }
        for edge in job["edges"]:
            issues: list[str] = []
            source_node = node_by_ref.get(edge["from_ref"])
            target_node = node_by_ref.get(edge["to_ref"])
            if source_node is None or target_node is None:
                issues.append("edge_endpoint_missing")
            if edge["relationship"] not in allowed_relationships:
                issues.append("relationship_not_in_schema")
            contract = contracts.get(edge["relationship"])
            if contract and source_node and not type_matches(source_node["type"], contract[0]):
                issues.append("from_type_mismatch")
            if contract and target_node and not type_matches(target_node["type"], contract[1]):
                issues.append("to_type_mismatch")
            if not edge["source"].strip():
                issues.append("source_required")
            from_id = source_node.get("selected_entity_id") if source_node else None
            to_id = target_node.get("selected_entity_id") if target_node else None
            if issues:
                status = "invalid"
            elif from_id and to_id and (from_id, edge["relationship"], to_id) in current_edges:
                status = "existing"
            elif source_node and target_node and source_node["match_status"] != "possible_duplicate" and target_node["match_status"] != "possible_duplicate":
                status = "new"
            else:
                status = "needs_review"
            edge["validation_issues"] = issues
            edge["match_status"] = status

    def _editable(self, import_id: str) -> dict:
        job = self.get(import_id)
        if job["status"] != "needs_review":
            raise AppError(409, "GRAPH_IMPORT_NOT_EDITABLE", "AI import không còn ở trạng thái review.")
        return job

    @staticmethod
    def _refresh_counts(job: dict) -> None:
        job["node_count"] = len(job.get("nodes", []))
        job["edge_count"] = len(job.get("edges", []))
        job["issue_count"] = sum(
            len(item.get("validation_issues", []))
            for item in [*job.get("nodes", []), *job.get("edges", [])]
        )

    @staticmethod
    def _content_version(content: str) -> str:
        import hashlib

        return hashlib.sha256(content.encode()).hexdigest()[:12]
