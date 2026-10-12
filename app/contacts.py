"""Async CardDAV access with bounded reads and single-attempt creation.

IDs are account-scoped resource hashes. They are resolved from fresh DAV
catalogues; callers never supply URLs, paths or vCards. No contact cache or
credential-bearing client is retained between operations.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import re
from typing import Any, AsyncIterator
from urllib.parse import urljoin, urlsplit
from uuid import uuid4
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring
import httpx
import vobject

from app.config import ContactsConfig
from app.contacts_schemas import ContactInput
from app.http_privacy import quiet_transport as _quiet_transport
from app.timing import measure_phase

DAV = "DAV:"
CARD = "urn:ietf:params:xml:ns:carddav"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_OPERATION_BYTES = 32 * 1024 * 1024
MAX_VCARD_BYTES = 256 * 1024
MULTIGET_BATCH_SIZE = 50
MAX_ADDRESSBOOKS = 128
_MESSAGES = {
    "not_configured": "Contacts require CARDDAV_USERNAME/CARDDAV_APP_PASSWORD or shared ICLOUD credentials.",
    "invalid_argument": "Use an exact returned ID, limit 1..500 and a nonnegative offset.",
    "addressbook_required": "Select an exact addressbook_id from list_addressbooks or configure CARDDAV_DEFAULT_ADDRESSBOOK.",
    "not_found": "The address book or contact is no longer available to this account.",
    "read_only": "This address book does not permit creating contacts.",
    "authentication_failed": "CardDAV authentication failed; check the account and app-specific password.",
    "access_denied": "CardDAV denied this operation.",
    "conflict": "The destination already exists; no overwrite was attempted.",
    "unsafe_target": "CardDAV returned a target outside the allowed HTTPS service or address book.",
    "response_too_large": "CardDAV exceeded the bounded response size; reduce the scope.",
    "coverage_incomplete": "The bounded address-book catalogue cannot establish whether this contact exists.",
    "protocol_error": "CardDAV returned an unsupported or invalid response.",
    "backend_unavailable": "CardDAV could not complete the operation.",
    "timeout": "The total CardDAV operation deadline expired.",
}


class ContactsError(Exception):
    def __init__(self, code: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(_MESSAGES[code])

    def payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": str(self)}, **self.details}


@dataclass
class _Operation:
    client: httpx.AsyncClient
    remaining_bytes: int = MAX_OPERATION_BYTES
    write: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Book:
    id: str
    url: str
    name: str
    writable: bool | None

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "writable": self.writable}


def _xml(tag: str, properties: tuple[str, ...]) -> bytes:
    root = ET.Element(tag)
    prop = ET.SubElement(root, f"{{{DAV}}}prop")
    for item in properties:
        ET.SubElement(prop, item)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _responses(data: bytes) -> list[tuple[str, dict[str, ET.Element], int]]:
    try:
        root = fromstring(data)
        if root.tag != f"{{{DAV}}}multistatus":
            raise ValueError
        entries = []
        for response in root.findall(f"{{{DAV}}}response"):
            href = response.findtext(f"{{{DAV}}}href")
            if not href:
                raise ValueError
            props = {}
            status = response.findtext(f"{{{DAV}}}status")
            code = int(status.split()[1]) if status else 200
            for propstat in response.findall(f"{{{DAV}}}propstat"):
                status = propstat.findtext(f"{{{DAV}}}status", "")
                if 200 <= int(status.split()[1]) < 300:
                    prop = propstat.find(f"{{{DAV}}}prop")
                    if prop is not None:
                        props.update({item.tag: item for item in prop})
            entries.append((href, props, code))
        return entries
    except Exception:
        raise ContactsError("protocol_error") from None


class ICloudContactsService:
    def __init__(self, config: ContactsConfig, *, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self._transport = transport
        self._origin = urlsplit(config.carddav_url)
        self._namespace = sha256((config.username + "\0" + config.carddav_url).encode()).hexdigest()
        self._safe_url(config.carddav_url, config.carddav_url)

    def _id(self, prefix: str, url: str) -> str:
        return prefix + sha256((self._namespace + "\0" + url).encode()).hexdigest()

    def _safe_url(self, base: str, href: str, *, book: _Book | None = None) -> str:
        try:
            if not href or any(ord(char) <= 32 or char == "\\" for char in href):
                raise ValueError
            target = urlsplit(urljoin(base, href))
            allowed = target.hostname == self._origin.hostname
            if self._origin.hostname == "contacts.icloud.com":
                allowed = allowed or bool(re.fullmatch(r"p\d+-contacts\.icloud\.com", target.hostname or ""))
            if (
                not allowed or target.scheme != "https" or target.port not in (None, 443)
                or target.username is not None or target.password is not None
                or target.query or target.fragment
            ):
                raise ValueError
            url = str(httpx.URL(target.geturl()))
            if book is not None:
                parent = httpx.URL(book.url)
                resource = httpx.URL(url)
                # Decoded paths prevent encoded traversal or separator escapes.
                if resource.host != parent.host or not resource.path.startswith(parent.path.rstrip("/") + "/"):
                    raise ValueError
                relative = resource.path[len(parent.path.rstrip("/") + "/"):]
                if not relative or "/" in relative or relative in (".", ".."):
                    raise ValueError
            return url
        except (ValueError, TypeError):
            raise ContactsError("unsafe_target") from None

    @asynccontextmanager
    async def _operation(self, *, write: bool = False) -> AsyncIterator[_Operation]:
        state = _Operation(httpx.AsyncClient(
            auth=httpx.BasicAuth(self.config.username, self.config.app_specific_password),
            timeout=self.config.timeout_seconds, follow_redirects=False, trust_env=False,
            transport=self._transport,
            headers={"User-Agent": "icloud-cruncher-carddav", "Accept-Encoding": "identity"},
        ), write={"write_status": "not_sent"} if write else {})
        try:
            with _quiet_transport(), measure_phase("contacts_service"):
                async with asyncio.timeout(self.config.timeout_seconds), state.client:
                    yield state
        except ContactsError as error:
            error.details.update(state.write)
            if state.write.get("write_status") == "succeeded":
                error.details["readback_confirmed"] = False
            raise
        except (TimeoutError, httpx.TimeoutException):
            details = dict(state.write)
            if details.get("write_status") == "succeeded":
                details["readback_confirmed"] = False
            raise ContactsError("timeout", **details) from None
        except Exception:
            details = dict(state.write)
            if details.get("write_status") == "succeeded":
                details["readback_confirmed"] = False
            raise ContactsError("backend_unavailable", **details) from None

    async def _request(
        self, state: _Operation, method: str, url: str, *, body: bytes = b"",
        depth: str | None = None, create: bool = False, book: _Book | None = None,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> tuple[int, bytes, httpx.Headers, str]:
        headers = {"Content-Type": "text/vcard; charset=utf-8" if create else "application/xml; charset=utf-8"}
        if depth is not None:
            headers["Depth"] = depth
        if create:
            headers["If-None-Match"] = "*"
        url = self._safe_url(url, url, book=book)
        for redirect in range(4):
            if create:
                state.write["write_status"] = "unknown"
            with measure_phase("carddav_request"):
                async with state.client.stream(method, url, headers=headers, content=body) as response:
                    status = response.status_code
                    if create and status == 201:
                        state.write["write_status"] = "succeeded"
                    elif create and 400 <= status < 500 and status != 408:
                        state.write["write_status"] = "failed"
                    if status in (301, 302, 303, 307, 308):
                        if create or redirect == 3:
                            raise ContactsError("protocol_error")
                        url = self._safe_url(url, response.headers.get("Location", ""), book=book)
                        continue
                    # Bodies are streamed and counted after decompression, even
                    # if the remote server ignores Accept-Encoding: identity.
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        state.remaining_bytes -= len(chunk)
                        if len(data) + len(chunk) > max_bytes or state.remaining_bytes < 0:
                            raise ContactsError("response_too_large")
                        data.extend(chunk)
                    return status, bytes(data), response.headers, url
        raise ContactsError("protocol_error")

    @staticmethod
    def _expect(status: int, allowed: tuple[int, ...]) -> None:
        if status in allowed:
            return
        code = {401: "authentication_failed", 403: "access_denied", 404: "not_found", 412: "conflict"}.get(status)
        raise ContactsError(code or ("backend_unavailable" if status >= 500 else "protocol_error"))

    async def _propfind(self, state: _Operation, url: str, properties: tuple[str, ...], depth: str = "0"):
        status, data, _, resolved = await self._request(
            state, "PROPFIND", url, body=_xml(f"{{{DAV}}}propfind", properties), depth=depth,
        )
        self._expect(status, (207,))
        return _responses(data), resolved

    async def _discover(self, state: _Operation) -> list[_Book]:
        with measure_phase("carddav_discovery"):
            base = self.config.carddav_url
            try:
                entries, resolved = await self._propfind(state, urljoin(base, "/.well-known/carddav"), (f"{{{DAV}}}current-user-principal",))
            except ContactsError as error:
                if error.code != "not_found":
                    raise
                entries, resolved = await self._propfind(state, base, (f"{{{DAV}}}current-user-principal",))
            principals = [props[f"{{{DAV}}}current-user-principal"].findtext(f"{{{DAV}}}href")
                          for _, props, _ in entries if f"{{{DAV}}}current-user-principal" in props]
            if len(principals) != 1 or not principals[0]:
                raise ContactsError("protocol_error")
            principal = self._safe_url(resolved, principals[0])
            entries, resolved = await self._propfind(state, principal, (f"{{{CARD}}}addressbook-home-set",))
            homes = [self._safe_url(resolved, node.text or "") for _, props, _ in entries
                     if f"{{{CARD}}}addressbook-home-set" in props
                     for node in props[f"{{{CARD}}}addressbook-home-set"].findall(f"{{{DAV}}}href")]
            if not homes or len(homes) > 8:
                raise ContactsError("protocol_error")
            books = {}
            for home in set(homes):
                entries, resolved = await self._propfind(state, home, (
                    f"{{{DAV}}}resourcetype", f"{{{DAV}}}displayname", f"{{{DAV}}}current-user-privilege-set",
                ), "1")
                for href, props, code in entries:
                    kind = props.get(f"{{{DAV}}}resourcetype")
                    if code >= 300 or kind is None or kind.find(f"{{{CARD}}}addressbook") is None:
                        continue
                    url = self._safe_url(resolved, href).rstrip("/") + "/"
                    permission = props.get(f"{{{DAV}}}current-user-privilege-set")
                    writable = None if permission is None else any(
                        permission.find(f".//{{{DAV}}}{name}") is not None for name in ("all", "write", "bind")
                    )
                    display = props.get(f"{{{DAV}}}displayname")
                    name = (display.text or "") if display is not None else ""
                    books[url] = _Book(self._id("ab_", url), url, name, writable)
                    if len(books) > MAX_ADDRESSBOOKS:
                        raise ContactsError("response_too_large")
            return sorted(books.values(), key=lambda item: item.id)

    def _select(self, books: list[_Book], addressbook_id: str | None, *, write: bool = False) -> _Book:
        if addressbook_id is not None and re.fullmatch(r"ab_[0-9a-f]{64}", addressbook_id) is None:
            raise ContactsError("invalid_argument")
        selected = addressbook_id or self.config.default_addressbook
        if selected:
            book = next((book for book in books if book.id == selected), None)
            if book is None:
                raise ContactsError("not_found")
        else:
            candidates = [book for book in books if not write or book.writable is not False]
            if len(candidates) != 1:
                raise ContactsError("addressbook_required")
            book = candidates[0]
        if write and book.writable is False:
            raise ContactsError("read_only")
        return book

    async def _catalogue(self, state: _Operation, book: _Book) -> tuple[list[tuple[str, str | None]], bool]:
        with measure_phase("carddav_catalogue"):
            entries, resolved = await self._propfind(state, book.url, (f"{{{DAV}}}resourcetype", f"{{{DAV}}}getetag"), "1")
            resources = {}
            complete = True
            for href, props, code in entries:
                url = self._safe_url(resolved, href)
                if url.rstrip("/") == book.url.rstrip("/"):
                    continue
                self._safe_url(resolved, href, book=book)
                kind = props.get(f"{{{DAV}}}resourcetype")
                if kind is not None and kind.find(f"{{{DAV}}}collection") is not None:
                    continue
                if code >= 300 or f"{{{DAV}}}getetag" not in props:
                    complete = False
                    continue
                resources[url] = props[f"{{{DAV}}}getetag"].text
            ordered = sorted(resources.items())
            return ordered[:self.config.max_contacts], complete and len(ordered) <= self.config.max_contacts

    async def list_addressbooks(self) -> dict[str, Any]:
        async with self._operation() as state:
            return {"addressbooks": [book.public() for book in await self._discover(state)]}

    async def _multiget(self, state: _Operation, book: _Book, resources: list[tuple[str, str | None]]):
        root = ET.Element(f"{{{CARD}}}addressbook-multiget")
        prop = ET.SubElement(root, f"{{{DAV}}}prop")
        ET.SubElement(prop, f"{{{DAV}}}getetag")
        ET.SubElement(prop, f"{{{CARD}}}address-data")
        wanted = {url for url, _ in resources}
        for url in wanted:
            ET.SubElement(root, f"{{{DAV}}}href").text = httpx.URL(url).raw_path.decode("ascii")
        status, data, _, resolved = await self._request(
            state, "REPORT", book.url, body=ET.tostring(root, encoding="utf-8"), depth="1",
        )
        self._expect(status, (207,))
        contacts = {}
        for href, props, code in _responses(data):
            url = self._safe_url(resolved, href, book=book)
            if url not in wanted or url in contacts:
                raise ContactsError("protocol_error")
            card = props.get(f"{{{CARD}}}address-data")
            if code >= 300 or card is None or not card.text:
                continue
            try:
                etag = props.get(f"{{{DAV}}}getetag")
                contacts[url] = self._parse(card.text, book, url, etag.text if etag is not None else None)
            except ContactsError as error:
                if error.code not in ("protocol_error", "response_too_large"):
                    raise
        return [contacts[url] for url, _ in resources if url in contacts], len(resources) - len(contacts)

    async def list_contacts(self, addressbook_id: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await self._page(addressbook_id, limit, offset)

    async def search_contacts(self, query: str, addressbook_id: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ContactsError("invalid_argument")
        return await self._page(addressbook_id, limit, offset, query)

    async def _page(self, addressbook_id: str | None, limit: int, offset: int, query: str | None = None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ContactsError("invalid_argument")
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= self.config.max_contacts:
            raise ContactsError("invalid_argument")
        async with self._operation() as state:
            book = self._select(await self._discover(state), addressbook_id)
            catalogue, complete = await self._catalogue(state, book)
            selected = catalogue if query is not None else catalogue[offset:offset + limit]
            contacts = []
            skipped = 0
            for start in range(0, len(selected), MULTIGET_BATCH_SIZE):
                batch, missing = await self._multiget(state, book, selected[start:start + MULTIGET_BATCH_SIZE])
                skipped += missing
                contacts.extend(batch if query is None else [contact for contact in batch if self._matches(contact, query)])
            total = len(contacts) if query is not None else len(catalogue)
            page = contacts[offset:offset + limit] if query is not None else contacts
            more = offset + limit < total
            return {
                "addressbook_id": book.id, "contacts": page, "offset": offset,
                "next_offset": offset + limit if more else None, "has_more": more,
                "coverage_complete": complete and skipped == 0, "skipped_count": skipped,
                "catalogue_count": len(catalogue),
            }

    @staticmethod
    def _matches(contact: dict[str, Any], query: str) -> bool:
        values = [contact[key] for key in ("display_name", "given_name", "family_name", "additional_name", "organization")]
        values.extend(item["value"] for key in ("emails", "phones") for item in contact[key])
        needle = query.strip().casefold()
        if any(needle in value.casefold() for value in values):
            return True
        digits = re.sub(r"\D", "", needle)
        return bool(digits and re.fullmatch(r"[\d\s+().-]+", needle) and any(
            digits in re.sub(r"\D", "", item["value"]) for item in contact["phones"]
        ))

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        if not isinstance(contact_id, str) or re.fullmatch(r"ct_[0-9a-f]{64}", contact_id) is None:
            raise ContactsError("invalid_argument")
        async with self._operation() as state:
            complete = True
            for book in await self._discover(state):
                catalogue, covered = await self._catalogue(state, book)
                complete = complete and covered
                for url, _ in catalogue:
                    if self._id("ct_", url) == contact_id:
                        return {"contact": await self._get(state, book, url)}
            raise ContactsError("not_found" if complete else "coverage_incomplete")

    async def _get(self, state: _Operation, book: _Book, url: str) -> dict[str, Any]:
        status, data, headers, _ = await self._request(state, "GET", url, book=book, max_bytes=MAX_VCARD_BYTES)
        self._expect(status, (200,))
        try:
            card = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ContactsError("protocol_error") from None
        return self._parse(card, book, url, headers.get("ETag"))

    async def create_contact(self, contact: ContactInput, addressbook_id: str | None = None) -> dict[str, Any]:
        # Serialization and all validation precede discovery and the write.
        uid = str(uuid4())
        card = self._serialize(contact, uid)
        async with self._operation(write=True) as state:
            book = self._select(await self._discover(state), addressbook_id, write=True)
            url = self._safe_url(book.url, uid + ".vcf", book=book)
            state.write.update(addressbook_id=book.id, contact_id=self._id("ct_", url), uid=uid)
            status, _, headers, _ = await self._request(state, "PUT", url, body=card, create=True, book=book)
            self._expect(status, (201,))
            try:
                saved = await self._get(state, book, url)
                if saved["uid"] != uid:
                    raise ContactsError("protocol_error")
            except ContactsError as error:
                return {**state.write, "readback_confirmed": False, "readback_error": error.code, "etag": headers.get("ETag")}
            return {**state.write, "readback_confirmed": True, "contact": saved}

    @staticmethod
    def _serialize(contact: ContactInput, uid: str) -> bytes:
        card = vobject.vCard()
        card.add("uid").value = uid
        card.add("fn").value = contact.display_name.strip() or " ".join(value.strip() for value in (
            contact.name_prefix, contact.given_name, contact.additional_name, contact.family_name, contact.name_suffix,
        ) if value.strip()) or contact.organization.strip()
        card.add("n").value = vobject.vcard.Name(
            family=contact.family_name, given=contact.given_name, additional=contact.additional_name,
            prefix=contact.name_prefix, suffix=contact.name_suffix,
        )
        if contact.organization:
            card.add("org").value = [contact.organization]
        if contact.notes:
            card.add("note").value = contact.notes
        if contact.birthday:
            card.add("bday").value = contact.birthday
        group = 0
        for key, items in (("email", contact.emails), ("tel", contact.phones), ("adr", contact.addresses)):
            for item in items:
                node = card.add(key)
                node.value = vobject.vcard.Address(
                    box=item.po_box, extended=item.extended, street=item.street, city=item.city,
                    region=item.region, code=item.postal_code, country=item.country,
                ) if key == "adr" else item.value
                if item.label:
                    group += 1
                    node.group = f"item{group}"
                    label = card.add("x-ablabel")
                    label.group = node.group
                    label.value = item.label
                    native_type = {"home": "HOME", "work": "WORK", "mobile": "CELL"}.get(item.label.casefold())
                    if native_type:
                        node.params["TYPE"] = [native_type]
        with _quiet_transport():
            data = card.serialize().encode("utf-8")
        if len(data) > MAX_VCARD_BYTES:
            raise ContactsError("response_too_large", write_status="not_sent")
        return data

    def _parse(self, text: str, book: _Book, url: str, etag: str | None) -> dict[str, Any]:
        if len(text.encode("utf-8")) > MAX_VCARD_BYTES:
            raise ContactsError("response_too_large")
        try:
            with _quiet_transport():
                cards = list(vobject.readComponents(text))
            if len(cards) != 1 or cards[0].name != "VCARD":
                raise ValueError
            card = cards[0]

            def value(key: str) -> str:
                nodes = card.contents.get(key, [])
                return self._text(nodes[0].value) if nodes else ""

            if value("kind").casefold() == "group" or value("x-addressbookserver-kind").casefold() == "group":
                raise ValueError

            labels = {node.group: self._text(node.value) for node in card.contents.get("x-ablabel", []) if node.group}

            def label(node) -> str:
                custom = labels.get(node.group)
                if custom is not None:
                    return custom.removeprefix("_$!<").removesuffix(">!$_")
                return "/".join(node.params.get("TYPE", []))

            names = card.contents.get("n", [])
            name = names[0].value if names else vobject.vcard.Name()
            result = {
                "id": self._id("ct_", url), "addressbook_id": book.id, "uid": value("uid"), "etag": etag,
                "display_name": value("fn"), "given_name": self._text(name.given),
                "family_name": self._text(name.family), "additional_name": self._text(name.additional),
                "name_prefix": self._text(name.prefix), "name_suffix": self._text(name.suffix),
                "organization": value("org"), "birthday": value("bday") or None, "notes": value("note"),
                "emails": [{"value": self._text(node.value), "label": label(node)} for node in card.contents.get("email", [])],
                "phones": [{"value": self._text(node.value), "label": label(node)} for node in card.contents.get("tel", [])],
                "addresses": [{
                    "label": label(node), **{public: self._text(getattr(node.value, native)) for public, native in (
                        ("po_box", "box"), ("extended", "extended"), ("street", "street"), ("city", "city"),
                        ("region", "region"), ("postal_code", "code"), ("country", "country"),
                    )},
                } for node in card.contents.get("adr", [])],
            }
            if not result["uid"]:
                raise ValueError
            return result
        except Exception:
            raise ContactsError("protocol_error") from None

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return "; ".join(str(item) for item in value)
        return str(value) if value is not None else ""
