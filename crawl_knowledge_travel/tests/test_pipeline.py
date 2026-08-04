from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from travel_crawl.collectors import WikidataCollector, _html_record, wikidata_record_from_binding
from travel_crawl.http_client import FetchResult
from travel_crawl.knowledge_graph import build_operational_graph
from travel_crawl.models import SourceRecord
from travel_crawl.storage import DatasetStore


class SourceRecordTests(unittest.TestCase):
    def test_stable_id_and_content_hash(self) -> None:
        first = SourceRecord.create(
            source="test", external_id="one", source_url="https://example.test/one",
            record_type="article", title="Một", license="test", text="Nội dung",
        )
        second = SourceRecord.create(
            source="test", external_id="one", source_url="https://example.test/one",
            record_type="article", title="Một", license="test", text="Nội dung",
        )
        self.assertEqual(first.record_id, second.record_id)
        self.assertEqual(first.content_sha256, second.content_sha256)

    def test_store_merges_by_record_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetStore(Path(directory), save_raw=False)
            record = SourceRecord.create(
                source="test", external_id="one", source_url="https://example.test/one",
                record_type="article", title="Một", license="test", text="Nội dung",
            )
            _, count_one = store.merge_records("test", [record])
            _, count_two = store.merge_records("test", [record])
            self.assertEqual(count_one, 1)
            self.assertEqual(count_two, 1)

    def test_wikidata_record_is_searchable_and_uses_https(self) -> None:
        record = wikidata_record_from_binding(
            {
                "item": {"value": "http://www.wikidata.org/entity/Q1"},
                "itemLabel": {"value": "Điểm tham quan", "xml:lang": "vi"},
                "itemDescription": {"value": "mô tả du lịch"},
                "type": {"value": "http://www.wikidata.org/entity/Q570116"},
                "typeLabel": {"value": "điểm tham quan"},
            },
            "tourism",
        )
        self.assertEqual(record.source_url, "https://www.wikidata.org/entity/Q1")
        self.assertIn("mô tả du lịch", record.text or "")
        self.assertNotIn("Q16917", {qid for values in WikidataCollector.ROOT_TYPES.values() for qid in values})

    def test_html_parser_keeps_headings_and_text(self) -> None:
        html = b"<html lang='vi'><head><title>Hue</title></head><body><main><h1>Hu\xc3\xa9</h1><h2>Tr\xe1\xba\xa3i nghi\xe1\xbb\x87m</h2><p>Tham quan di s\xe1\xba\xa3n v\xc3\xa0 \xe1\xba\xa9m th\xe1\xbb\xb1c \xc4\x91\xe1\xbb\x8ba ph\xc6\xb0\xc6\xa1ng trong m\xe1\xbb\x99t h\xc3\xa0nh tr\xc3\xacnh c\xc3\xb3 ngu\xe1\xbb\x93n.</p></main></body></html>"
        result = FetchResult(
            url="https://example.test/hue", status_code=200, content=html,
            headers={"content-type": "text/html; charset=utf-8"},
        )
        record = _html_record(
            source="test", license_name="test", result=result, record_type="article"
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIn("Trải nghiệm", record.sections)
        self.assertIn("ẩm thực địa phương", record.text or "")

    def test_html_parser_uses_nonempty_title_and_absolute_canonical_url(self) -> None:
        html = b"""<html lang='vi'><head>
        <meta property='og:title' content='Pho co Ha Noi'>
        <link rel='canonical' href='/ha-noi/pho-co'>
        </head><body><main><h1></h1><p>This article has enough useful travel content for normalization and downstream review.</p></main></body></html>"""
        result = FetchResult(
            url="https://example.test/articles/one", status_code=200, content=html,
            headers={"content-type": "text/html; charset=utf-8"},
        )
        record = _html_record(
            source="test", license_name="test", result=result, record_type="article"
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.title, "Pho co Ha Noi")
        self.assertEqual(record.source_url, "https://example.test/ha-noi/pho-co")


class KnowledgeGraphBuildTests(unittest.TestCase):
    def test_builder_links_evidence_without_copying_article_text(self) -> None:
        base_graph = {
            "schemaVersion": "travel-knowledge-graph.v1",
            "regionKey": "vn,ha-noi",
            "regionAliases": ["Hanoi", "Hà Nội"],
            "nodes": [
                {
                    "id": "exp:museum",
                    "kind": "experience",
                    "label": "history museum",
                    "aliases": ["museum", "bảo tàng"],
                    "searchTerms": ["history museum"],
                }
            ],
            "edges": [],
        }
        hanoi = SourceRecord.create(
            source="wikidata",
            external_id="Q1",
            source_url="https://www.wikidata.org/entity/Q1",
            record_type="wikidata_entity",
            title="Bảo tàng Hà Nội",
            license="CC0-1.0",
            text="Raw prose must not enter the operational graph.",
            destination_hints=["Hà Nội"],
            payload={"typeLabel": "viện bảo tàng"},
        ).to_dict()
        hue = SourceRecord.create(
            source="wikidata",
            external_id="Q2",
            source_url="https://www.wikidata.org/entity/Q2",
            record_type="wikidata_entity",
            title="Bảo tàng Huế",
            license="CC0-1.0",
            destination_hints=["Huế"],
            payload={"typeLabel": "viện bảo tàng"},
        ).to_dict()

        graph = build_operational_graph(
            base_graph,
            [hanoi, hue],
            built_at="2026-08-02T00:00:00+00:00",
        )

        self.assertEqual(graph["build"]["inputRecordCount"], 2)
        self.assertEqual(graph["build"]["regionRelevantRecordCount"], 1)
        self.assertEqual(len(graph["sources"]), 1)
        self.assertNotIn("text", graph["sources"][0])
        self.assertEqual(
            graph["nodes"][0]["evidenceRefs"][0]["sourceId"],
            hanoi["record_id"],
        )

    def test_builder_does_not_confuse_pho_with_thanh_pho(self) -> None:
        graph = build_operational_graph(
            {
                "schemaVersion": "travel-knowledge-graph.v1",
                "regionKey": "vn,ha-noi",
                "regionAliases": ["Hà Nội"],
                "nodes": [
                    {
                        "id": "exp:pho",
                        "kind": "experience",
                        "label": "phở",
                        "aliases": ["pho", "phở"],
                    }
                ],
                "edges": [],
            },
            [
                SourceRecord.create(
                    source="dsvh",
                    external_id="one",
                    source_url="https://dsvh.gov.vn/thanh-pho-ha-noi",
                    record_type="vietnam_cultural_heritage",
                    title="Di tích tại thành phố Hà Nội",
                    license="official-reference-with-attribution",
                ).to_dict()
            ],
            built_at="2026-08-02T00:00:00+00:00",
        )

        self.assertNotIn("evidenceRefs", graph["nodes"][0])


if __name__ == "__main__":
    unittest.main()
