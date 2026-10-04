"""Brevo (Sendinblue) v3 API client — backend-only, contact & list management only.
No email sending. No list/automation creation except the explicit create_list() call
which the app only invokes after Super Admin confirmation. The API key is read from the
BREVO_API_KEY environment variable and is NEVER returned, logged, or stored in the DB.
"""
import os
from urllib.parse import quote

import httpx

BASE_URL = "https://api.brevo.com/v3"
# Custom contact attributes CRMEvent would like to populate when present in the account.
DESIRED_ATTRS = ["ORGANIZZAZIONE", "EVENTO", "SPORT", "REGIONE", "CITTA", "SITO",
                 "INSTAGRAM", "LINKEDIN", "FONTE", "DATA_ACQUISIZIONE", "STATO_LEAD"]
PROSPECT_LIST_NAME = "CRMEvent – Prospect"
PROSPECT_TEMPLATE_NAME = "CRMEvent · Funnel Prospect · Email 1"


class BrevoNotConfigured(Exception):
    pass


class BrevoError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        msg = body.get("message") if isinstance(body, dict) else str(body)
        super().__init__(f"Brevo HTTP {status}: {msg}")


def api_key():
    return os.environ.get("BREVO_API_KEY")


def is_configured():
    return bool(api_key())


class BrevoClient:
    def __init__(self, timeout: float = 20):
        key = api_key()
        if not key:
            raise BrevoNotConfigured("BREVO_API_KEY non configurata")
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"accept": "application/json", "content-type": "application/json", "api-key": key},
            timeout=timeout,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        await self.client.aclose()

    async def _req(self, method, path, **kw):
        r = await self.client.request(method, path, **kw)
        try:
            body = r.json() if r.content else None
        except ValueError:
            body = r.text[:500]
        if r.is_error:
            raise BrevoError(r.status_code, body)  # body never contains the api-key
        return body

    async def account(self):
        return await self._req("GET", "/account")

    async def lists(self, limit=50):
        out, offset = [], 0
        while True:
            page = await self._req("GET", "/contacts/lists", params={"limit": limit, "offset": offset, "sort": "asc"})
            chunk = (page or {}).get("lists", [])
            out.extend(chunk)
            if len(chunk) < limit:
                break
            offset += limit
        return out

    async def attributes(self):
        page = await self._req("GET", "/contacts/attributes")
        return (page or {}).get("attributes", [])

    async def senders(self):
        page = await self._req("GET", "/senders")
        return (page or {}).get("senders", [])

    async def create_list(self, name, folder_id):
        return await self._req("POST", "/contacts/lists", json={"name": name, "folderId": folder_id})

    async def get_list(self, list_id):
        """List detail incl. totalSubscribers / uniqueSubscribers (contatti letti da Brevo)."""
        return await self._req("GET", f"/contacts/lists/{list_id}")

    async def folders(self, limit=50):
        page = await self._req("GET", "/contacts/folders", params={"limit": limit, "offset": 0})
        return (page or {}).get("folders", [])

    async def get_contact(self, email):
        """Returns the contact dict, or None on 404 (not a contact yet)."""
        ident = quote(email, safe="")
        try:
            return await self._req("GET", f"/contacts/{ident}")
        except BrevoError as e:
            if e.status == 404:
                return None
            raise

    async def create_contact(self, email, list_id, attributes=None):
        payload = {"email": email, "listIds": [list_id], "updateEnabled": False}
        if attributes:
            payload["attributes"] = attributes
        return await self._req("POST", "/contacts", json=payload)

    async def add_existing_to_list(self, email, list_id):
        # ONLY listIds — never send EMAIL/emailBlacklisted, so we never resubscribe.
        ident = quote(email, safe="")
        return await self._req("PUT", f"/contacts/{ident}", json={"listIds": [list_id]})

    async def update_contact(self, email, list_id=None, attributes=None):
        """Update an existing contact WITHOUT resubscribing (emailBlacklisted is NEVER sent).
        Optionally add to a list and/or refresh custom attributes. No duplicate is created."""
        ident = quote(email, safe="")
        payload = {}
        if list_id is not None:
            payload["listIds"] = [list_id]
        if attributes:
            payload["attributes"] = {k: v for k, v in attributes.items() if v is not None}
        if not payload:
            return None
        return await self._req("PUT", f"/contacts/{ident}", json=payload)

    async def get_templates(self, limit=50):
        out, offset = [], 0
        while True:
            page = await self._req("GET", "/smtp/templates", params={"limit": limit, "offset": offset, "sort": "desc"})
            chunk = (page or {}).get("templates", [])
            out.extend(chunk)
            if len(chunk) < limit:
                break
            offset += limit
        return out

    async def create_email_template(self, name, subject, html, sender, tag=None):
        """Create a DRAFT email template (isActive=False). Never sends. sender = {name,email} or {id}."""
        payload = {"templateName": name, "subject": subject, "htmlContent": html,
                   "sender": sender, "isActive": False}
        if tag:
            payload["tag"] = tag
        return await self._req("POST", "/smtp/templates", json=payload)

    async def activate_template(self, template_id):
        """Attiva un template transazionale (Bozza -> Attivo) via API Brevo.
        PUT /smtp/templates/{id} {isActive:true} -> 204. Non tocca il DB CRMEvent."""
        return await self._req("PUT", f"/smtp/templates/{template_id}", json={"isActive": True})
