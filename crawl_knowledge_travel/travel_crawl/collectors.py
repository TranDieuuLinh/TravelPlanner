from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections import deque
from html import unescape
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from .http_client import FetchResult, PoliteHttpClient
from .models import SourceRecord, utc_now
from .storage import DatasetStore


logger = logging.getLogger(__name__)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def wikidata_record_from_binding(binding: dict, group: str) -> SourceRecord:
    item_url = binding["item"]["value"]
    qid = item_url.rsplit("/", 1)[-1]
    title = binding.get("itemLabel", {}).get("value", qid)
    payload = {
        key: value.get("value")
        for key, value in binding.items()
        if isinstance(value, dict) and value.get("value") is not None
    }
    description = payload.get("itemDescription", "")
    type_label = payload.get("typeLabel", "")
    searchable_text = ". ".join(value for value in (title, description, type_label) if value)
    return SourceRecord.create(
        source="wikidata",
        external_id=qid,
        source_url=item_url.replace("http://", "https://", 1),
        record_type="wikidata_entity",
        title=title,
        license="CC0-1.0",
        language=binding.get("itemLabel", {}).get("xml:lang"),
        text=searchable_text,
        destination_hints=[payload["adminLabel"]] if payload.get("adminLabel") else [],
        payload={"queryGroup": group, "qid": qid, **payload},
    )


def _html_record(
    *,
    source: str,
    license_name: str,
    result: FetchResult,
    record_type: str,
    destination_hints: list[str] | None = None,
) -> SourceRecord | None:
    # Decode ourselves because several Vietnamese official sites omit or send an
    # inaccurate charset header.  Passing bytes makes BeautifulSoup guess again.
    soup = BeautifulSoup(result.text, "lxml")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    title = ""
    for selector in ("h1", "meta[property='og:title']", "title"):
        title_tag = soup.select_one(selector)
        if title_tag:
            candidate = title_tag.get("content", "") if title_tag.name == "meta" else title_tag.get_text(" ", strip=True)
            title = _clean_text(candidate)
            if title:
                break
    if not title:
        title = result.url
    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        return None
    text = _clean_text(main.get_text(" ", strip=True))
    if len(text) < 80:
        return None
    sections: dict[str, str] = {}
    for heading in main.find_all(["h2", "h3"]):
        name = _clean_text(heading.get_text(" ", strip=True))
        values: list[str] = []
        for sibling in heading.next_siblings:
            sibling_name = getattr(sibling, "name", None)
            if sibling_name in {"h2", "h3"}:
                break
            if hasattr(sibling, "get_text"):
                candidate = _clean_text(sibling.get_text(" ", strip=True))
                if candidate:
                    values.append(candidate)
            if sum(map(len, values)) >= 5000:
                break
        if name and values:
            sections[name] = " ".join(values)[:5000]
    canonical = soup.find("link", rel="canonical")
    canonical_url = urljoin(result.url, canonical.get("href")) if canonical and canonical.get("href") else result.url
    return SourceRecord.create(
        source=source,
        external_id=canonical_url,
        source_url=canonical_url,
        record_type=record_type,
        title=title,
        license=license_name,
        retrieved_at=utc_now(),
        language=(soup.html.get("lang") if soup.html else None),
        text=text,
        destination_hints=destination_hints,
        sections=sections,
        payload={"finalUrl": result.url},
    )


class BaseCollector(ABC):
    source: str

    def __init__(self, client: PoliteHttpClient, store: DatasetStore, *, limit: int = 0) -> None:
        self.client = client
        self.store = store
        self.limit = limit

    def reached_limit(self, records: list[SourceRecord]) -> bool:
        return self.limit > 0 and len(records) >= self.limit

    def save_response(self, result: FetchResult) -> None:
        self.store.save_raw(
            source=self.source,
            url=result.url,
            content=result.content,
            content_type=result.headers.get("content-type", "application/octet-stream"),
            status_code=result.status_code,
            headers=result.headers,
        )

    @abstractmethod
    def collect(self) -> list[SourceRecord]: ...


class WikidataCollector(BaseCollector):
    source = "wikidata"
    endpoint = "https://query.wikidata.org/sparql"

    ROOT_TYPES = {
        "tourism": ["Q570116", "Q33506", "Q4989906", "Q839954", "Q15243209"],
        "heritage_places": ["Q9259", "Q210272", "Q2977", "Q811979", "Q4989906"],
        "nature": ["Q46169", "Q473972", "Q40080", "Q8502", "Q23397", "Q35509", "Q4022"],
        "culture": ["Q132241", "Q184485", "Q2207288", "Q24398318", "Q856584", "Q2065736", "Q16970"],
    }

    def _query(self, group: str, *, page_size: int, offset: int) -> str:
        values = " ".join(f"wd:{qid}" for qid in self.ROOT_TYPES[group])
        return f"""
SELECT DISTINCT ?item ?itemLabel ?itemDescription ?type ?typeLabel ?coord
                ?admin ?adminLabel ?heritage ?heritageLabel ?article WHERE {{
  VALUES ?rootType {{ {values} }}
  ?item wdt:P17 wd:Q881;
        wdt:P31 ?rootType.
  BIND(?rootType AS ?type)
  OPTIONAL {{ ?item wdt:P625 ?coord. }}
  OPTIONAL {{ ?item wdt:P131 ?admin. }}
  OPTIONAL {{ ?item wdt:P1435 ?heritage. }}
  OPTIONAL {{ ?article schema:about ?item; schema:isPartOf <https://vi.wikipedia.org/>. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "vi,en". }}
}}
ORDER BY ?item
LIMIT {page_size}
OFFSET {offset}
""".strip()

    def collect(self) -> list[SourceRecord]:
        records: dict[str, SourceRecord] = {}
        groups = list(self.ROOT_TYPES)
        for group_index, group in enumerate(groups):
            # A global limit is shared fairly so a large first class cannot
            # crowd nature, culture and heritage out of the result entirely.
            if self.limit > 0:
                base, extra = divmod(self.limit, len(groups))
                group_limit = base + (1 if group_index < extra else 0)
            else:
                group_limit = 0
            group_binding_count = 0
            offset = 0
            while group_limit <= 0 or group_binding_count < group_limit:
                remaining = 500 if group_limit <= 0 else min(500, group_limit - group_binding_count)
                if remaining <= 0:
                    break
                try:
                    result = self.client.get(
                        self.endpoint,
                        params={"query": self._query(group, page_size=remaining, offset=offset), "format": "json"},
                        respect_robots=False,
                    )
                except RuntimeError as exc:
                    logger.warning("Skipping Wikidata group %s after repeated source errors: %s", group, exc)
                    break
                self.save_response(result)
                data = json.loads(result.text)
                bindings = data.get("results", {}).get("bindings", [])
                if not bindings:
                    break
                for binding in bindings:
                    record = wikidata_record_from_binding(binding, group)
                    records[record.record_id] = record
                group_binding_count += len(bindings)
                if len(bindings) < remaining:
                    break
                offset += remaining
        return list(records.values())


class WikivoyageCollector(BaseCollector):
    source = "wikivoyage"
    endpoint = "https://en.wikivoyage.org/w/api.php"

    def _api(self, params: dict[str, object]) -> dict:
        result = self.client.get(self.endpoint, params={"format": "json", "formatversion": 2, **params}, respect_robots=False)
        self.save_response(result)
        return json.loads(result.text)

    def _discover_pages(self) -> list[dict]:
        categories = deque([("Category:Vietnam", 0)])
        seen_categories: set[str] = set()
        pages: dict[int, dict] = {}
        while categories and (self.limit <= 0 or len(pages) < self.limit):
            category, depth = categories.popleft()
            if category in seen_categories or depth > 4:
                continue
            seen_categories.add(category)
            continuation: str | None = None
            while True:
                params: dict[str, object] = {
                    "action": "query", "list": "categorymembers", "cmtitle": category,
                    "cmtype": "page|subcat", "cmlimit": "max",
                }
                if continuation:
                    params["cmcontinue"] = continuation
                try:
                    data = self._api(params)
                except RuntimeError as exc:
                    logger.warning("Skipping Wikivoyage category %s after repeated source errors: %s", category, exc)
                    break
                for item in data.get("query", {}).get("categorymembers", []):
                    if item.get("ns") == 14:
                        categories.append((item["title"], depth + 1))
                    elif item.get("ns") == 0:
                        pages[int(item["pageid"])] = item
                        if self.limit > 0 and len(pages) >= self.limit:
                            break
                continuation = data.get("continue", {}).get("cmcontinue")
                if not continuation or (self.limit > 0 and len(pages) >= self.limit):
                    break
        return list(pages.values())

    def collect(self) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        existing_page_ids = {
            int(record.payload["pageId"])
            for record in self.store.load_records(self.source).values()
            if record.payload.get("pageId") is not None
        }
        for page in self._discover_pages():
            if int(page["pageid"]) in existing_page_ids:
                continue
            try:
                data = self._api({"action": "parse", "pageid": page["pageid"], "prop": "text|sections|categories"})
            except RuntimeError as exc:
                logger.warning("Skipping Wikivoyage page %s after repeated source errors: %s", page["title"], exc)
                continue
            parsed = data.get("parse")
            if not parsed:
                continue
            html = parsed.get("text", "")
            soup = BeautifulSoup(html, "lxml")
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            text = _clean_text(soup.get_text(" ", strip=True))
            if len(text) < 80:
                continue
            title = parsed.get("title", page["title"])
            sections = {
                section.get("line", f"section-{index}"): section.get("anchor", "")
                for index, section in enumerate(parsed.get("sections", []))
            }
            records.append(SourceRecord.create(
                source=self.source,
                external_id=str(page["pageid"]),
                source_url=f"https://en.wikivoyage.org/wiki/{quote(title.replace(' ', '_'))}",
                record_type="travel_guide",
                title=title,
                license="CC-BY-SA-4.0",
                language="en",
                text=text,
                destination_hints=[title],
                payload={
                    "pageId": page["pageid"],
                    "sections": sections,
                    "categories": [item.get("category") for item in parsed.get("categories", [])],
                },
            ))
            if self.reached_limit(records):
                break
        return records


class SitemapSiteCollector(BaseCollector):
    seed_urls: tuple[str, ...] = ()
    relevant_markers: tuple[str, ...] = ()
    license_name = "official-reference"
    record_type = "official_travel_article"

    def _sitemap_urls(self) -> list[str]:
        queue = deque(self.seed_urls)
        seen: set[str] = set()
        pages: list[str] = []
        while queue and len(seen) < 100:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            try:
                result = self.client.get(url, respect_robots=False)
            except RuntimeError:
                continue
            self.save_response(result)
            try:
                root = ET.fromstring(result.content)
            except ET.ParseError:
                continue
            locations = [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]
            if root.tag.endswith("sitemapindex"):
                queue.extend(locations)
            else:
                pages.extend(url for url in locations if self._relevant(url))
        return list(dict.fromkeys(pages))

    def _relevant(self, url: str) -> bool:
        lowered = url.casefold()
        return any(marker in lowered for marker in self.relevant_markers)

    def _fallback_links(self) -> list[str]:
        pages: list[str] = []
        origins = {f"{urlparse(seed).scheme}://{urlparse(seed).netloc}" for seed in self.seed_urls}
        for origin in origins:
            try:
                result = self.client.get(origin)
            except (RuntimeError, PermissionError):
                continue
            self.save_response(result)
            soup = BeautifulSoup(result.text, "lxml")
            for anchor in soup.find_all("a", href=True):
                url = urljoin(result.url, anchor["href"])
                if urlparse(url).netloc == urlparse(origin).netloc and self._relevant(url):
                    pages.append(url)
        return list(dict.fromkeys(pages))

    def collect(self) -> list[SourceRecord]:
        pages = self._sitemap_urls() or self._fallback_links()
        records: list[SourceRecord] = []
        for url in pages:
            if self.reached_limit(records):
                break
            try:
                result = self.client.get(url)
            except (RuntimeError, PermissionError) as exc:
                logger.warning("Skipping %s: %s", url, exc)
                continue
            self.save_response(result)
            record = _html_record(
                source=self.source,
                license_name=self.license_name,
                result=result,
                record_type=self.record_type,
            )
            if record:
                records.append(record)
        return records


class VietnamTravelCollector(SitemapSiteCollector):
    source = "vietnam_travel"
    seed_urls = (
        "https://vietnam.travel/sitemap.xml",
        "https://vietnam.travel/sitemap_index.xml",
    )
    relevant_markers = (
        "/places-to-go/", "/things-to-do/", "/plan-your-trip/",
        "/heritage-sites-vietnam", "/vietnamese-culture", "/vietnamese-food",
    )


class LinkCatalogCollector(BaseCollector):
    license_name = "official-reference"
    catalog_urls: tuple[str, ...] = ()
    detail_patterns: tuple[re.Pattern[str], ...] = ()
    record_type = "official_reference"

    def _allowed_detail(self, url: str, _label: str = "") -> bool:
        return any(pattern.search(url) for pattern in self.detail_patterns)

    def collect(self) -> list[SourceRecord]:
        detail_urls: list[str] = []
        records: list[SourceRecord] = []
        for catalog_url in self.catalog_urls:
            try:
                result = self.client.get(catalog_url)
            except (RuntimeError, PermissionError) as exc:
                logger.warning("Skipping catalog %s: %s", catalog_url, exc)
                continue
            self.save_response(result)
            catalog_record = _html_record(
                source=self.source,
                license_name=self.license_name,
                result=result,
                record_type=f"{self.record_type}_catalog",
            )
            if catalog_record:
                records.append(catalog_record)
            soup = BeautifulSoup(result.content, "lxml")
            for anchor in soup.find_all("a", href=True):
                url = urljoin(result.url, anchor["href"])
                if self._allowed_detail(url, _clean_text(anchor.get_text(" ", strip=True))):
                    detail_urls.append(url)
        for url in dict.fromkeys(detail_urls):
            if self.reached_limit(records):
                break
            try:
                result = self.client.get(url)
            except (RuntimeError, PermissionError) as exc:
                logger.warning("Skipping detail %s: %s", url, exc)
                continue
            self.save_response(result)
            record = _html_record(
                source=self.source,
                license_name=self.license_name,
                result=result,
                record_type=self.record_type,
            )
            if record:
                records.append(record)
        return records


class UnescoCollector(LinkCatalogCollector):
    source = "unesco"
    catalog_urls = (
        "https://whc.unesco.org/en/statesparties/vn",
        "https://ich.unesco.org/en/state/viet-nam-VN?cp=VN&info=elements-on-the-lists&topic=en-state",
    )
    detail_patterns = (
        re.compile(r"^https://whc\.unesco\.org/en/list/\d+"),
        re.compile(r"^https://ich\.unesco\.org/en/(?:RL|USL|BSP)/[^?#]+"),
    )
    record_type = "unesco_heritage"


class CulturalHeritageVietnamCollector(LinkCatalogCollector):
    source = "dsvh"
    catalog_urls = (
        "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-dac-biet-1752",
        "https://dsvh.gov.vn/danh-muc-di-san-van-hoa-va-thien-nhien-the-gioi-1751",
        "https://dsvh.gov.vn/di-san-van-hoa-phi-vat-the-1748",
    )
    detail_patterns = (
        re.compile(r"^https://dsvh\.gov\.vn/(?!Upload/|ckfinder/)[^?#]+-\d+$", re.IGNORECASE),
    )
    record_type = "vietnam_cultural_heritage"
    license_name = "official-reference-with-attribution"

    _excluded_navigation_ids = {
        "1745", "1746", "1747", "1748", "1749", "1750", "1751", "1752",
        "1753", "1754", "1755", "1756", "1757", "1758",
    }
    _heritage_markers = (
        "di tích", "di sản", "lễ hội", "danh thắng", "bảo vật", "thành",
        "đền", "chùa", "làng", "nghề", "vườn quốc gia", "heritage",
    )

    def _allowed_detail(self, url: str, label: str = "") -> bool:
        if not super()._allowed_detail(url, label):
            return False
        match = re.search(r"-(\d+)$", urlparse(url).path)
        if match and match.group(1) in self._excluded_navigation_ids:
            return False
        candidate = f"{urlparse(url).path} {label}".casefold()
        return any(marker in candidate for marker in self._heritage_markers)


COLLECTOR_TYPES = {
    "wikidata": WikidataCollector,
    "wikivoyage": WikivoyageCollector,
    "vietnam_travel": VietnamTravelCollector,
    "unesco": UnescoCollector,
    "dsvh": CulturalHeritageVietnamCollector,
}
