"""Bounded, source-grounded public enrichment providers for partner research."""

from __future__ import annotations

import ipaddress
import io
import json
import re
import socket
import zipfile
from datetime import datetime, timedelta
from urllib import robotparser
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

import requests


USER_AGENT = "MirrorTalkPartnerResearch/1.0 (source-grounded partnership research)"


class PartnerSourceError(RuntimeError):
    pass


@dataclass
class SourceEvidence:
    provider: str
    source_url: str
    source_title: str
    fact_text: str
    evidence_type: str = "organisation_fact"
    confidence: str = "medium"
    published_at: str = ""


@dataclass
class ContactObservation:
    provider: str
    source_url: str
    contact_email: str = ""
    contact_name: str = ""
    role_title: str = ""
    confidence: str = "medium"
    verification_status: str = "published"
    evidence_text: str = ""


@dataclass
class ProviderResult:
    provider: str
    evidence: List[SourceEvidence] = field(default_factory=list)
    contacts: List[ContactObservation] = field(default_factory=list)
    discovered_orcid_ids: List[str] = field(default_factory=list)


def _safe_public_url(url: str, *, allowed_host: str = "") -> str:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not host:
        raise PartnerSourceError("Provider returned an invalid source URL.")
    if allowed_host and host not in {allowed_host, f"www.{allowed_host}"} and allowed_host not in {host, f"www.{host}"}:
        raise PartnerSourceError("First-party research cannot leave the organisation host.")
    try:
        for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            address = ipaddress.ip_address(item[4][0])
            if not address.is_global:
                raise PartnerSourceError("Private or local network sources are not allowed.")
    except socket.gaierror as exc:
        raise PartnerSourceError("Source host could not be resolved.") from exc
    return parsed.geturl()


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.text: List[str] = []
        self.links: List[str] = []
        self.json_ld: List[str] = []
        self._json = False
        self._json_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        values = dict(attrs)
        if tag == "title": self._in_title = True
        if tag == "a" and values.get("href"): self.links.append(values["href"] or "")
        if tag == "script" and values.get("type", "").casefold() == "application/ld+json":
            self._json = True; self._json_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title": self._in_title = False
        if tag == "script" and self._json:
            self.json_ld.append("".join(self._json_parts)); self._json = False

    def handle_data(self, data: str) -> None:
        if self._in_title: self.title += data
        if self._json: self._json_parts.append(data)
        elif data.strip(): self.text.append(data.strip())


class PublicSourceClient:
    def __init__(self, *, timeout_seconds: float = 8.0, session: Any = requests):
        self.timeout_seconds = timeout_seconds
        self.session = session

    def _get(self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> requests.Response:
        try:
            response = self.session.get(url, params=params, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=self.timeout_seconds)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise PartnerSourceError("Public provider request failed.") from exc

    def first_party(self, organisation: str, website: str) -> ProviderResult:
        parsed = urlparse(website)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        root = f"{parsed.scheme}://{parsed.netloc}"
        urls = [website, *(f"{root}/{path}" for path in ("about", "team", "leadership", "partnerships", "press", "news", "contact"))]
        result = ProviderResult("first_party")
        seen = set()
        robots = robotparser.RobotFileParser()
        try:
            robots.set_url(f"{root}/robots.txt")
            robots.parse(self._get(f"{root}/robots.txt").text.splitlines())
        except PartnerSourceError:
            robots = None
        for candidate in urls[:8]:
            try:
                url = _safe_public_url(candidate, allowed_host=host)
                if robots is not None and not robots.can_fetch(USER_AGENT, url):
                    continue
                response = self._get(url)
            except PartnerSourceError:
                continue
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type and "text" not in content_type: continue
            parser = _PageParser(); parser.feed(response.text[:500_000])
            plain = re.sub(r"\s+", " ", " ".join(parser.text)).strip()
            if len(plain) >= 80:
                fact = plain[:480].rstrip()
                digest = (url, fact)
                if digest not in seen:
                    result.evidence.append(SourceEvidence("first_party", url, parser.title.strip() or organisation, fact, "first_party_profile", "high")); seen.add(digest)
            emails = set(re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", response.text, re.I))
            for email in sorted(emails)[:8]:
                result.contacts.append(ContactObservation("first_party", url, contact_email=email,
                    role_title="Published organisation contact", confidence="high" if email.casefold().endswith(f"@{host}") else "medium",
                    evidence_text=f"The organisation publishes {email} on this page."))
            for raw in parser.json_ld[:10]:
                try: objects = json.loads(raw); objects = objects if isinstance(objects, list) else [objects]
                except (TypeError, ValueError): continue
                for obj in objects:
                    if not isinstance(obj, dict): continue
                    name = str(obj.get("name") or "").strip(); role = str(obj.get("jobTitle") or "").strip()
                    if name and role:
                        result.contacts.append(ContactObservation("first_party_jsonld", url, contact_name=name, role_title=role,
                            confidence="high", evidence_text=f"First-party structured data identifies {name} as {role}."))
                    values = json.dumps(obj)
                    result.discovered_orcid_ids.extend(re.findall(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", values))
        result.discovered_orcid_ids = list(dict.fromkeys(result.discovered_orcid_ids))
        return result

    def media_feeds(self, organisation: str, website: str) -> ProviderResult:
        parsed = urlparse(website); root = f"{parsed.scheme}://{parsed.netloc}"; host = (parsed.hostname or "").casefold().removeprefix("www.")
        result = ProviderResult("media_feeds")
        for path in ("feed", "rss", "feed.xml", "rss.xml", "sitemap.xml"):
            url = f"{root}/{path}"
            try:
                _safe_public_url(url, allowed_host=host); response = self._get(url)
                tree = ElementTree.fromstring(response.content[:1_000_000])
            except (PartnerSourceError, ElementTree.ParseError): continue
            items = tree.findall(".//item") + tree.findall(".//{*}entry") + tree.findall(".//{*}url")
            for item in items[:8]:
                title = (item.findtext("title") or item.findtext("{*}title") or "").strip()
                link = (item.findtext("link") or item.findtext("{*}loc") or "").strip()
                if not link:
                    link_node = item.find("{*}link"); link = (link_node.attrib.get("href", "") if link_node is not None else "")
                link = urljoin(root, link)
                published = (item.findtext("pubDate") or item.findtext("{*}published") or item.findtext("{*}lastmod") or "").strip()
                if title and link:
                    result.evidence.append(SourceEvidence("media_feeds", link, title, f"{organisation} published or listed “{title}”.", "timely_signal", "high", published))
        return result

    def wikidata(self, organisation: str) -> ProviderResult:
        response = self._get("https://www.wikidata.org/w/api.php", params={"action":"wbsearchentities","search":organisation,"language":"en","format":"json","limit":3,"type":"item"})
        result = ProviderResult("wikidata")
        for item in (response.json().get("search") or [])[:3]:
            label = str(item.get("label") or ""); description = str(item.get("description") or ""); source = str(item.get("concepturi") or "")
            if label and description and source:
                result.evidence.append(SourceEvidence("wikidata", source, label, f"Wikidata describes {label} as {description}.", "structured_identity", "medium"))
        return result

    def openalex(self, organisation: str) -> ProviderResult:
        response = self._get("https://api.openalex.org/institutions", params={"search":organisation,"per-page":3,"mailto":"team@mirrortalkpodcast.com"})
        result = ProviderResult("openalex")
        institutions = (response.json().get("results") or [])[:3]
        for item in institutions:
            name = str(item.get("display_name") or ""); url = str(item.get("id") or "")
            if name and url:
                fact = f"OpenAlex identifies {name} as a {item.get('type') or 'research organisation'} with {int(item.get('works_count') or 0):,} indexed works."
                result.evidence.append(SourceEvidence("openalex", url, name, fact, "research_authority", "medium"))
        if not institutions:
            works = self._get("https://api.openalex.org/works", params={"search":organisation,"per-page":5,"mailto":"team@mirrortalkpodcast.com"})
            for item in (works.json().get("results") or [])[:5]:
                title = str(item.get("display_name") or item.get("title") or "").strip(); url = str(item.get("id") or "").strip()
                if title and url:
                    year = item.get("publication_year")
                    suffix = f" ({year})" if year else ""
                    result.evidence.append(SourceEvidence("openalex", url, title, f"OpenAlex found the indexed work “{title}”{suffix} while researching {organisation}; verify the relationship before use.", "research_signal", "low", str(year or "")))
        return result

    def crossref(self, organisation: str) -> ProviderResult:
        response = self._get("https://api.crossref.org/works", params={"query.publisher-name":organisation,"rows":5,"select":"DOI,title,publisher,published,URL"})
        result = ProviderResult("crossref")
        for item in ((response.json().get("message") or {}).get("items") or [])[:5]:
            title = str((item.get("title") or [""])[0]).strip(); url = str(item.get("URL") or "").strip(); publisher = str(item.get("publisher") or "").strip()
            if title and url:
                result.evidence.append(SourceEvidence("crossref", url, title, f"Crossref indexes “{title}” from {publisher or organisation}.", "publication_signal", "medium"))
        return result

    def gdelt(self, organisation: str) -> ProviderResult:
        result = ProviderResult("gdelt")
        try:
            response = self._get("https://api.gdeltproject.org/api/v2/doc/doc", params={"query":f'"{organisation}"',"mode":"artlist","maxrecords":8,"format":"json","sort":"datedesc","timespan":"6months"})
            for item in (response.json().get("articles") or [])[:8]:
                title = str(item.get("title") or "").strip(); url = str(item.get("url") or "").strip()
                if title and url:
                    result.evidence.append(SourceEvidence("gdelt", url, title, f"GDELT discovered recent coverage titled “{title}”; editorial review is required.", "news_signal", "low", str(item.get("seendate") or "")))
            return result
        except (PartnerSourceError, ValueError):
            pass
        latest = self._get("https://data.gdeltproject.org/gdeltv2/lastupdate.txt")
        gkg_line = next((line for line in latest.text.splitlines() if ".gkg.csv.zip" in line), "")
        parts = gkg_line.split()
        if len(parts) < 3:
            raise PartnerSourceError("GDELT latest-update feed did not identify a GKG snapshot.")
        archive = None
        archive_url = parts[2].replace("http://", "https://")
        timestamp_match = re.search(r"/(\d{14})\.gkg\.csv\.zip$", archive_url)
        candidates = [archive_url]
        if timestamp_match:
            latest_at = datetime.strptime(timestamp_match.group(1), "%Y%m%d%H%M%S")
            candidates.extend(
                re.sub(r"/\d{14}\.gkg\.csv\.zip$", f"/{(latest_at - timedelta(minutes=15 * offset)).strftime('%Y%m%d%H%M%S')}.gkg.csv.zip", archive_url)
                for offset in range(1, 9)
            )
        for candidate in candidates:
            try:
                archive = self._get(candidate)
                break
            except PartnerSourceError:
                continue
        if archive is None:
            raise PartnerSourceError("GDELT did not expose a recent readable GKG snapshot.")
        if len(archive.content) > 8_000_000:
            raise PartnerSourceError("GDELT snapshot exceeded the bounded download size.")
        try:
            with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
                name = bundle.namelist()[0]
                with bundle.open(name) as stream:
                    for raw in stream:
                        row = raw.decode("utf-8", errors="ignore").rstrip("\n").split("\t")
                        if len(row) < 15 or organisation.casefold() not in f"{row[13]} {row[14]}".casefold():
                            continue
                        url = row[4].strip(); source = row[3].strip() or "GDELT source"
                        if url.startswith(("http://", "https://")):
                            result.evidence.append(SourceEvidence("gdelt", url, source, f"GDELT's latest public knowledge-graph snapshot mentions {organisation} in coverage from {source}; editorial review is required.", "news_signal", "low", row[1].strip()))
                        if len(result.evidence) >= 8: break
        except (zipfile.BadZipFile, IndexError) as exc:
            raise PartnerSourceError("GDELT returned an unreadable public snapshot.") from exc
        return result

    def orcid(self, orcid_ids: Iterable[str], organisation: str = "") -> ProviderResult:
        result = ProviderResult("orcid")
        identifiers = list(dict.fromkeys(orcid_ids))[:5]
        if not identifiers and organisation:
            response = self._get("https://pub.orcid.org/v3.0/expanded-search/", params={"q":f'affiliation-org-name:"{organisation}"',"rows":5}, headers={"Accept":"application/json"})
            for item in (response.json().get("expanded-result") or [])[:5]:
                orcid_id = str(item.get("orcid-id") or "").strip()
                name = " ".join(part for part in (str(item.get("given-names") or "").strip(), str(item.get("family-names") or "").strip()) if part)
                if orcid_id:
                    result.evidence.append(SourceEvidence("orcid", f"https://orcid.org/{orcid_id}", f"ORCID profile for {name or orcid_id}", f"ORCID affiliation search associates the public profile for {name or orcid_id} with {organisation}; verify current affiliation before use.", "person_identity", "medium"))
            return result
        for orcid_id in identifiers:
            try: response = self._get(f"https://pub.orcid.org/v3.0/{quote(orcid_id)}/record", headers={"Accept":"application/json"})
            except PartnerSourceError: continue
            value = response.json(); person = value.get("person") or {}; name = person.get("name") or {}
            credit = ((name.get("credit-name") or {}).get("value") or "").strip()
            if credit:
                result.evidence.append(SourceEvidence("orcid", f"https://orcid.org/{orcid_id}", f"ORCID profile for {credit}", f"ORCID identifies this public researcher profile as {credit}.", "person_identity", "high"))
        return result


def default_public_providers() -> tuple[str, ...]:
    return ("first_party", "media_feeds", "wikidata", "openalex", "crossref", "gdelt", "orcid")
