import asyncio
from dataclasses import replace
import logging
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx
import pytest
import vobject

from app.config import ContactsConfig
from app.contacts import CARD, DAV, ContactsError, ICloudContactsService, MAX_VCARD_BYTES
from app.contacts_schemas import ContactInput

ORIGIN = "https://contacts.icloud.com"
PARTITION = "https://p42-contacts.icloud.com"
PRINCIPAL = "/private-account/principal/"
HOME = "/private-account/addressbooks/"
BOOK = HOME + "default/"
PRIVATE_CARD = """BEGIN:VCARD\r
VERSION:3.0\r
UID:native-contact-uid\r
FN:Änne Example\r
N:Example;Änne;Maria;Dr.;\r
ORG:Example Company;Research\r
item1.EMAIL;TYPE=HOME:anne@example.invalid\r
item1.X-ABLabel:_$!<Home>!$_\r
EMAIL;TYPE=WORK:a@example.invalid\r
TEL;TYPE=CELL:+49 (170) 123-45\r
TEL;TYPE=WORK:+49 30 5555\r
ADR;TYPE=HOME:;;First street 1;Berlin;Berlin;10115;Germany\r
BDAY:2000-02-29\r
NOTE:First line\\nSecond line\\; literal semicolon\r
END:VCARD\r
"""


def multistatus(entries):
    root = ET.Element(f"{{{DAV}}}multistatus")
    for href, properties, status in entries:
        response = ET.SubElement(root, f"{{{DAV}}}response")
        ET.SubElement(response, f"{{{DAV}}}href").text = href
        if status != 200:
            ET.SubElement(response, f"{{{DAV}}}status").text = f"HTTP/1.1 {status} Error"
            continue
        propstat = ET.SubElement(response, f"{{{DAV}}}propstat")
        ET.SubElement(propstat, f"{{{DAV}}}status").text = "HTTP/1.1 200 OK"
        prop = ET.SubElement(propstat, f"{{{DAV}}}prop")
        for tag, value in properties.items():
            node = ET.SubElement(prop, tag)
            if isinstance(value, list):
                for child, text in value:
                    ET.SubElement(node, child).text = text
            else:
                node.text = value
    return ET.tostring(root, encoding="utf-8")


class CardDAV:
    def __init__(self):
        self.requests = []
        self.books = [BOOK]
        self.writable = True
        self.cards = {BOOK + "existing.vcf": PRIVATE_CARD}
        self.etag = '"native-etag"'
        self.put_status = 201
        self.put_exception = None
        self.readback_status = 200
        self.readback_delay = 0
        self.home_href = HOME
        self.resource_href = None
        self.report_override = None
        self.initial_redirect = None
        self.well_known_missing = False
        self.puts = []
        self.request_delay = 0
        self.saved_display_name = None

    async def __call__(self, request):
        self.requests.append(request)
        assert request.headers["authorization"].startswith("Basic ")
        if self.request_delay:
            await asyncio.sleep(self.request_delay)
        path = request.url.path
        if path == "/.well-known/carddav":
            if self.well_known_missing:
                return httpx.Response(404)
            if self.initial_redirect:
                return httpx.Response(301, headers={"Location": self.initial_redirect})
        if request.method == "PROPFIND":
            properties = ET.fromstring(request.content).find(f"{{{DAV}}}prop")
            if properties.find(f"{{{DAV}}}current-user-principal") is not None:
                return httpx.Response(207, content=multistatus([(path, {
                    f"{{{DAV}}}current-user-principal": [(f"{{{DAV}}}href", PARTITION + PRINCIPAL)],
                }, 200)]))
            if path == PRINCIPAL:
                return httpx.Response(207, content=multistatus([(path, {
                    f"{{{CARD}}}addressbook-home-set": [(f"{{{DAV}}}href", self.home_href)],
                }, 200)]))
            if path == HOME:
                rows = []
                for index, book in enumerate(self.books):
                    props = {
                        f"{{{DAV}}}resourcetype": [(f"{{{DAV}}}collection", None), (f"{{{CARD}}}addressbook", None)],
                        f"{{{DAV}}}displayname": "Private Book " + str(index),
                    }
                    if self.writable is not None:
                        props[f"{{{DAV}}}current-user-privilege-set"] = [(f"{{{DAV}}}bind" if self.writable else f"{{{DAV}}}read", None)]
                    rows.append((book, props, 200))
                return httpx.Response(207, content=multistatus(rows))
            if path in self.books:
                rows = [(path, {f"{{{DAV}}}resourcetype": [(f"{{{DAV}}}collection", None)]}, 200)]
                rows.extend((self.resource_href or href, {f"{{{DAV}}}getetag": self.etag}, 200)
                            for href in self.cards if href.startswith(path))
                return httpx.Response(207, content=multistatus(rows))
        if request.method == "REPORT":
            if self.report_override is not None:
                return httpx.Response(207, content=self.report_override)
            hrefs = ET.fromstring(request.content).findall(f"{{{DAV}}}href")
            rows = [(node.text, {f"{{{DAV}}}getetag": self.etag, f"{{{CARD}}}address-data": self.cards[node.text]}, 200)
                    if node.text in self.cards else (node.text, {}, 404) for node in hrefs]
            return httpx.Response(207, content=multistatus(rows))
        if request.method == "PUT":
            self.puts.append(request)
            if self.put_status == 201:
                self.cards[path] = request.content.decode("utf-8")
                if self.saved_display_name:
                    saved = vobject.readOne(self.cards[path])
                    saved.fn.value = self.saved_display_name
                    self.cards[path] = saved.serialize()
            if self.put_exception:
                raise self.put_exception
            return httpx.Response(self.put_status, headers={"ETag": self.etag})
        if request.method == "GET":
            if self.readback_delay:
                await asyncio.sleep(self.readback_delay)
            if self.readback_status != 200:
                return httpx.Response(self.readback_status)
            return httpx.Response(200 if path in self.cards else 404, content=self.cards.get(path, ""), headers={"ETag": self.etag})
        raise AssertionError("Unexpected mock DAV request")


@pytest.fixture
def dav():
    return CardDAV()


def service(dav, **overrides):
    config = replace(ContactsConfig("private-account@example.invalid", "private-password"), **overrides)
    return ICloudContactsService(config, transport=httpx.MockTransport(dav))


def run(awaitable):
    return asyncio.run(awaitable)


def test_discovery_resolves_partition_and_returns_no_server_paths(dav):
    result = run(service(dav).list_addressbooks())
    assert len(result["addressbooks"]) == 1
    assert result["addressbooks"][0]["writable"] is True
    assert result["addressbooks"][0]["id"].startswith("ab_")
    assert [request.url.host for request in dav.requests] == ["contacts.icloud.com", "p42-contacts.icloud.com", "p42-contacts.icloud.com"]
    assert PRINCIPAL not in str(result)
    assert HOME not in str(result)


def test_well_known_falls_back_to_root(dav):
    dav.well_known_missing = True
    assert len(run(service(dav).list_addressbooks())["addressbooks"]) == 1
    assert dav.requests[1].url.path == "/"


def test_partition_redirect_is_allowed(dav):
    dav.initial_redirect = PARTITION + "/discovery/"
    assert len(run(service(dav).list_addressbooks())["addressbooks"]) == 1
    assert dav.requests[1].url.host == "p42-contacts.icloud.com"


@pytest.mark.parametrize("target", [
    "https://evil.invalid/steal/", "http://p42-contacts.icloud.com/plain/",
    "https://p42-contacts.icloud.com:444/", "https://someone@p42-contacts.icloud.com/",
    "https://mail.icloud.com/", "https://contacts.icloud.com.evil.invalid/", "//evil.invalid/",
])
@pytest.mark.parametrize("source", ["initial_redirect", "home_href"])
def test_untrusted_discovery_and_redirects_receive_no_credentials(dav, source, target):
    setattr(dav, source, target)
    with pytest.raises(ContactsError) as error:
        run(service(dav).list_addressbooks())
    assert error.value.code == "unsafe_target"
    assert all(request.url.host in ("contacts.icloud.com", "p42-contacts.icloud.com") for request in dav.requests)


def test_native_fields_labels_and_multivalues_are_preserved(dav):
    result = run(service(dav).list_contacts())
    contact = result["contacts"][0]
    assert result["coverage_complete"] is True
    assert contact["given_name"] == "Änne"
    assert contact["additional_name"] == "Maria"
    assert contact["name_prefix"] == "Dr."
    assert contact["organization"] == "Example Company; Research"
    assert contact["emails"] == [
        {"value": "anne@example.invalid", "label": "Home"}, {"value": "a@example.invalid", "label": "WORK"},
    ]
    assert len(contact["phones"]) == 2
    assert contact["addresses"][0]["postal_code"] == "10115"
    assert contact["birthday"] == "2000-02-29"
    assert contact["notes"] == "First line\nSecond line; literal semicolon"
    assert contact["etag"] == dav.etag


@pytest.mark.parametrize("query", ["ÄNNE", "RESEARCH", "ANNE@EXAMPLE", "+4917012345"])
def test_search_matches_unicode_organization_email_and_formatted_phones(dav, query):
    result = run(service(dav).search_contacts(query))
    assert len(result["contacts"]) == 1
    assert result["coverage_complete"] is True


def test_list_pagination_fetches_only_the_selected_page(dav):
    dav.cards[BOOK + "z-last.vcf"] = PRIVATE_CARD.replace("native-contact-uid", "second-uid")
    result = run(service(dav).list_contacts(limit=1))
    assert result["has_more"] is True
    assert result["next_offset"] == 1
    reports = [request for request in dav.requests if request.method == "REPORT"]
    assert len(ET.fromstring(reports[0].content).findall(f"{{{DAV}}}href")) == 1
    second = run(service(dav).list_contacts(limit=1, offset=1))
    assert second["has_more"] is False
    assert second["contacts"][0]["id"] != result["contacts"][0]["id"]


def test_search_pagination_keeps_separate_duplicates(dav):
    dav.cards[BOOK + "duplicate.vcf"] = PRIVATE_CARD.replace("native-contact-uid", "second-uid")
    first = run(service(dav).search_contacts("Änne", limit=1))
    second = run(service(dav).search_contacts("Änne", limit=1, offset=1))
    assert first["next_offset"] == 1
    assert second["next_offset"] is None
    assert first["contacts"][0]["id"] != second["contacts"][0]["id"]


def test_bounded_catalogue_marks_search_incomplete(dav):
    dav.cards[BOOK + "z-last.vcf"] = PRIVATE_CARD.replace("Änne", "Last")
    result = run(service(dav, max_contacts=1).search_contacts("Last"))
    assert result["contacts"] == []
    assert result["coverage_complete"] is False
    assert result["catalogue_count"] == 1


def test_malformed_or_oversized_cards_do_not_claim_complete_coverage(dav):
    dav.cards[BOOK + "bad.vcf"] = "PRIVATE MALFORMED CARD"
    dav.cards[BOOK + "oversized.vcf"] = PRIVATE_CARD + "x" * MAX_VCARD_BYTES
    result = run(service(dav).list_contacts())
    assert len(result["contacts"]) == 1
    assert result["coverage_complete"] is False
    assert result["skipped_count"] == 2


@pytest.mark.parametrize("href", [HOME + "other/escape.vcf", BOOK + "../escape.vcf", BOOK + "%2e%2e/escape.vcf", "https://evil.invalid/stolen.vcf"])
def test_catalogue_cannot_escape_selected_addressbook(dav, href):
    dav.resource_href = href
    with pytest.raises(ContactsError) as error:
        run(service(dav).list_contacts())
    assert error.value.code == "unsafe_target"
    assert not any(request.method == "REPORT" for request in dav.requests)


def test_get_uses_stable_account_scoped_resource_id_after_restart(dav):
    result = run(service(dav).list_contacts())
    identifier = result["contacts"][0]["id"]
    fresh = run(service(dav).get_contact(identifier))
    assert fresh["contact"]["uid"] == "native-contact-uid"
    other = service(dav)
    other.config = replace(other.config, username="other-account")
    other = ICloudContactsService(other.config, transport=httpx.MockTransport(dav))
    with pytest.raises(ContactsError) as error:
        run(other.get_contact(identifier))
    assert error.value.code == "not_found"


def test_ambiguous_addressbook_prevents_writes_and_exact_id_selects(dav):
    dav.books.append(HOME + "second/")
    contacts = service(dav)
    with pytest.raises(ContactsError) as error:
        run(contacts.create_contact(ContactInput(given_name="New")))
    assert error.value.code == "addressbook_required"
    assert error.value.details["write_status"] == "not_sent"
    assert dav.puts == []
    books = run(contacts.list_addressbooks())["addressbooks"]
    created = run(contacts.create_contact(ContactInput(given_name="New"), books[0]["id"]))
    assert created["addressbook_id"] == books[0]["id"]


def test_configured_default_addressbook_is_an_exact_id(dav):
    dav.books.append(HOME + "second/")
    identifier = run(service(dav).list_addressbooks())["addressbooks"][0]["id"]
    assert run(service(dav, default_addressbook=identifier).list_contacts())["addressbook_id"] == identifier
    with pytest.raises(ContactsError) as error:
        run(service(dav, default_addressbook="Private Book 0").list_contacts())
    assert error.value.code == "not_found"


def test_current_read_only_permissions_prevent_creation(dav):
    contacts = service(dav)
    identifier = run(contacts.list_addressbooks())["addressbooks"][0]["id"]
    dav.writable = False
    with pytest.raises(ContactsError) as error:
        run(contacts.create_contact(ContactInput(organization="Company"), identifier))
    assert error.value.code == "read_only"
    assert error.value.details["write_status"] == "not_sent"
    assert dav.puts == []


def test_unknown_privileges_are_reported_without_guessing(dav):
    dav.writable = None
    assert run(service(dav).list_addressbooks())["addressbooks"][0]["writable"] is None


def test_create_serializes_utf8_escaping_and_multiple_fields_once(dav):
    contact = ContactInput(
        given_name="Änne", family_name="Example;comma,", organization="Research",
        emails=[{"value": "first@example.invalid", "label": "work"}, {"value": "second@example.invalid", "label": "Privat"}],
        phones=[{"value": "+49 170 123", "label": "mobile"}],
        addresses=[{"street": "First street\nSecond line", "city": "Berlin", "label": "home"}],
        birthday="2000-02-29", notes="Line one\nFN:must remain note text; a comma, and a slash\\",
    )
    result = run(service(dav).create_contact(contact))
    assert result["write_status"] == "succeeded"
    assert result["readback_confirmed"] is True
    assert result["contact"]["notes"] == contact.notes
    assert len(result["contact"]["emails"]) == 2
    assert result["contact"]["addresses"][0]["street"] == contact.addresses[0].street
    assert len(dav.puts) == 1
    request = dav.puts[0]
    assert request.headers["if-none-match"] == "*"
    assert request.url.path.endswith(result["uid"] + ".vcf")
    native = vobject.readOne(request.content.decode("utf-8"))
    assert len(native.contents["fn"]) == 1
    assert native.n.value.family == "Example;comma,"
    assert native.tel.params["TYPE"] == ["CELL"]
    # A fresh read sees the new resource without any cached list state.
    assert run(service(dav).get_contact(result["contact_id"]))["contact"]["uid"] == result["uid"]


@pytest.mark.parametrize("status,code", [(401, "authentication_failed"), (403, "access_denied"), (412, "conflict"), (500, "backend_unavailable"), (408, "protocol_error"), (302, "protocol_error")])
def test_failed_create_never_retries_and_preserves_reference(dav, status, code):
    dav.put_status = status
    with pytest.raises(ContactsError) as error:
        run(service(dav).create_contact(ContactInput(given_name="New")))
    assert error.value.code == code
    assert error.value.details["write_status"] == ("failed" if 400 <= status < 500 and status != 408 else "unknown")
    assert error.value.details["contact_id"].startswith("ct_")
    assert error.value.details["uid"]
    assert len(dav.puts) == 1


def test_uncertain_creation_can_be_reconciled_by_get_without_replay(dav):
    dav.put_exception = httpx.ReadTimeout("PRIVATE transport detail")
    with pytest.raises(ContactsError) as error:
        run(service(dav).create_contact(ContactInput(given_name="New")))
    assert error.value.code == "timeout"
    assert error.value.details["write_status"] == "unknown"
    result = run(service(dav).get_contact(error.value.details["contact_id"]))
    assert result["contact"]["uid"] == error.value.details["uid"]
    assert len(dav.puts) == 1
    assert "PRIVATE" not in str(error.value)


def test_confirmed_creation_survives_failed_readback(dav):
    dav.readback_status = 503
    result = run(service(dav).create_contact(ContactInput(organization="New Company")))
    assert result["write_status"] == "succeeded"
    assert result["readback_confirmed"] is False
    assert result["contact_id"]
    assert len(dav.puts) == 1


def test_total_deadline_preserves_confirmed_creation(dav):
    dav.readback_delay = 0.2
    with pytest.raises(ContactsError) as error:
        run(service(dav, timeout_seconds=0.05).create_contact(ContactInput(given_name="New")))
    assert error.value.code == "timeout"
    assert error.value.details["write_status"] == "succeeded"
    assert error.value.details["readback_confirmed"] is False
    assert error.value.details["contact_id"]
    assert len(dav.puts) == 1


def test_total_deadline_applies_to_discovery_not_only_individual_requests(dav):
    dav.request_delay = 0.025
    with pytest.raises(ContactsError) as error:
        run(service(dav, timeout_seconds=0.04).list_addressbooks())
    assert error.value.code == "timeout"


def test_unrequested_report_resources_and_xml_entities_are_rejected(dav):
    dav.report_override = multistatus([(BOOK + "unrequested.vcf", {f"{{{CARD}}}address-data": PRIVATE_CARD}, 200)])
    with pytest.raises(ContactsError) as error:
        run(service(dav).list_contacts())
    assert error.value.code == "protocol_error"
    dav.report_override = b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><d:multistatus xmlns:d="DAV:">&x;</d:multistatus>'
    with pytest.raises(ContactsError) as error:
        run(service(dav).list_contacts())
    assert error.value.code == "protocol_error"


def test_groups_are_skipped_instead_of_being_exposed_as_people(dav):
    dav.cards[BOOK + "group.vcf"] = PRIVATE_CARD.replace("UID:native-contact-uid", "UID:group-uid\r\nX-ADDRESSBOOKSERVER-KIND:group")
    result = run(service(dav).list_contacts())
    assert len(result["contacts"]) == 1
    assert result["skipped_count"] == 1
    assert result["coverage_complete"] is False


def test_get_rejects_oversized_vcard_before_parsing(dav):
    contacts = service(dav)
    identifier = run(contacts.list_contacts())["contacts"][0]["id"]
    dav.cards[BOOK + "existing.vcf"] = PRIVATE_CARD + "x" * MAX_VCARD_BYTES
    with pytest.raises(ContactsError) as error:
        run(contacts.get_contact(identifier))
    assert error.value.code == "response_too_large"


def test_missing_contact_under_partial_coverage_is_distinct_from_not_found(dav):
    full = run(service(dav).list_contacts())["contacts"][0]["id"]
    dav.cards[BOOK + "a-first.vcf"] = PRIVATE_CARD.replace("native-contact-uid", "other-uid")
    with pytest.raises(ContactsError) as error:
        run(service(dav, max_contacts=1).get_contact(full))
    assert error.value.code == "coverage_incomplete"


def test_byte_budget_is_enforced_while_streaming(dav, monkeypatch):
    import app.contacts as backend
    # The operation dataclass default is fixed at import time; replace the
    # bounded counter in the test session without changing request defaults.
    original = backend._Operation

    def tiny_operation(*arguments, **options):
        return original(*arguments, **options, remaining_bytes=100)

    monkeypatch.setattr(backend, "_Operation", tiny_operation)
    with pytest.raises(ContactsError) as error:
        run(service(dav).list_addressbooks())
    assert error.value.code == "response_too_large"


def test_search_fetches_in_bounded_multiget_batches(dav):
    dav.cards = {BOOK + f"{index:03d}.vcf": PRIVATE_CARD.replace("native-contact-uid", f"uid-{index}") for index in range(51)}
    result = run(service(dav).search_contacts("Änne", limit=2))
    assert result["has_more"] is True
    assert len(result["contacts"]) == 2
    reports = [request for request in dav.requests if request.method == "REPORT"]
    assert sorted(len(ET.fromstring(request.content).findall(f"{{{DAV}}}href")) for request in reports) == [1, 50]


def test_create_returns_native_readback_instead_of_echoing_input(dav):
    dav.saved_display_name = "Server-normalized name"
    result = run(service(dav).create_contact(ContactInput(given_name="New")))
    assert result["contact"]["display_name"] == "Server-normalized name"
    assert result["readback_confirmed"] is True


@pytest.mark.parametrize("identifier", ["", "Private Book 0", PARTITION + BOOK])
def test_invalid_addressbook_selectors_prevent_creation(dav, identifier):
    with pytest.raises(ContactsError) as error:
        run(service(dav).create_contact(ContactInput(given_name="New"), identifier))
    assert error.value.code == "invalid_argument"
    assert error.value.details["write_status"] == "not_sent"
    assert dav.puts == []


def test_http_and_vcard_logs_do_not_expose_private_content(dav, caplog):
    with caplog.at_level(logging.DEBUG):
        run(service(dav).list_contacts())
        run(service(dav).create_contact(ContactInput(given_name="SECRET_CONTACT_NAME")))
    for private in ("private-account", "private-password", "Änne", "SECRET_CONTACT_NAME", "native-contact-uid", "existing.vcf"):
        assert private not in caplog.text


@pytest.mark.parametrize("arguments", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": True}])
def test_invalid_pagination_never_contacts_server(dav, arguments):
    with pytest.raises(ContactsError):
        run(service(dav).list_contacts(**arguments))
    assert dav.requests == []
