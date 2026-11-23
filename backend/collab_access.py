"""Collaboratori per evento (scheda evento) + gestione accessi account da Super Admin.
Riusa memberships/permessi/inviti esistenti: nessun secondo sistema di autenticazione."""
import re
from datetime import datetime, timezone, timedelta
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
import permissions as P

STATUS_LABEL = {"active": "Attivo", "disabled": "Disattivato", "revoked": "Revocato", "pending": "Invito in attesa"}


class PermIn(BaseModel):
    sections: Optional[dict] = None
    flags: Optional[dict] = None


class CollabInviteIn(PermIn):
    nome: str
    cognome: str
    email: EmailStr


class EventActionIn(PermIn):
    action: str  # disable | restore | revoke | assign
    reason: Optional[str] = None


class StateIn(BaseModel):
    active: bool
    reason: Optional[str] = None


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require_admin, require_superadmin, audit = deps["require_admin"], deps["require_superadmin"], deps["record_audit"]
    now_iso, new_id = deps["now_iso"], deps["new_id"]

    def _perm(m: dict) -> dict:
        return P.normalize_permissions(m.get("permissions"), m.get("role") or "user")

    def _apply(base: dict, body: PermIn, cap: Optional[dict] = None) -> dict:
        """Sezioni (livelli) e permessi delicati; cap = permessi di chi concede (mai oltre i propri)."""
        raw = {**base}
        if body.sections is not None:  # sezioni non indicate = nessun accesso
            raw["sections"] = {k: [a for a in P.ACTIONS if a in (body.sections.get(k) or [])] for k in P.SECTION_KEYS}
        for f in P.FLAGS:
            if body.flags and f in body.flags:
                raw[f] = body.flags[f] is True
        out = P.normalize_permissions(raw, "collaboratore")
        if cap and not cap.get("admin"):
            out["sections"] = {k: [a for a in v if a in (cap.get("sections") or {}).get(k, [])] for k, v in out["sections"].items()}
            for f in P.FLAGS:
                out[f] = out[f] and bool(cap.get(f))
        return out

    def _summary(p: dict) -> str:
        secs = [f"{lbl}: {'modifica' if len(p['sections'].get(k, [])) > 1 else 'visualizza'}" for k, lbl in P.SECTIONS if p["sections"].get(k) and k not in P.HIDDEN_SECTIONS]
        fl = [lbl for f, lbl in P.FLAGS.items() if p.get(f)]
        return ("; ".join(secs) or "nessuna sezione") + (f" · delicati: {', '.join(fl)}" if fl else "")

    async def _event(org_id: str, eid: str) -> dict:
        ev = await db.events.find_one({"org_id": org_id, "id": eid}, {"_id": 0, "id": 1, "nome": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        return ev

    async def _can_manage(user: dict, eid: str) -> dict:
        perm = user.get("perm") or {}
        if perm.get("admin"):
            return perm
        if not perm.get("manage_permissions"):
            raise HTTPException(status_code=403, detail="Serve il permesso specifico «Gestione permessi collaboratori»")
        if perm.get("event_ids") is not None and eid not in perm["event_ids"]:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        return perm

    async def _set_event(m: dict, eid: str, status: Optional[str], actor: dict, reason: Optional[str] = None, perm: Optional[dict] = None):
        """status None = accesso attivo; disabled = sospeso (config conservata); revoked = tolto dalla lista."""
        p = perm or _perm(m)
        evs = p["events"]
        if evs == "all" and status:  # esplicita la lista per poter escludere un solo evento
            evs = await db.events.distinct("id", {"org_id": m["org_id"]})
        evs = list(evs) if evs != "all" else "all"
        if evs != "all":
            if status == "revoked":
                evs = [e for e in evs if e != eid]
            elif eid not in evs:
                evs.append(eid)
        p = {**p, "events": evs}
        states = dict(m.get("event_states") or {})
        if status:
            states[eid] = {"status": status, "at": now_iso(), "by": actor.get("email"), "reason": (reason or "").strip() or None}
        else:
            states.pop(eid, None)
        await db.memberships.update_one({"id": m["id"]}, {"$set": {"permissions": p, "event_states": states, "updated_at": now_iso()}})
        return p

    def _event_status(m: dict, eid: str) -> Optional[str]:
        st = ((m.get("event_states") or {}).get(eid) or {}).get("status")
        if st:
            return st
        evs = _perm(m)["events"]
        return "active" if evs == "all" or eid in evs else None

    async def _send(inv: dict, org: dict) -> bool:
        try:
            await deps["send_invite_email"](inv["email"], org.get("nome"), inv["token"], inv["role"], nome=inv.get("nome"))
            return True
        except Exception:
            return False

    # ---------------- Scheda evento: Collaboratori ----------------
    @r.get("/events/{event_id}/collaborators")
    async def list_collab(event_id: str, user: dict = Depends(require_admin)):
        org_id = user["org_id"]
        await _event(org_id, event_id)
        cap = await _can_manage(user, event_id)
        mems = await db.memberships.find({"org_id": org_id, "role": "collaboratore"}, {"_id": 0}).to_list(2000)
        rows = []
        uids = [m["user_id"] for m in mems]
        users = {u["user_id"]: u for u in await db.users.find({"user_id": {"$in": uids}}, {"_id": 0, "password_hash": 0}).to_list(2000)}
        for m in mems:
            st = _event_status(m, event_id)
            if not st:
                continue
            u = users.get(m["user_id"]) or {}
            acc = "disabled" if u.get("active") is False or m.get("active") is False else st
            p = _perm(m)
            rows.append({"kind": "member", "user_id": m["user_id"], "name": u.get("name"), "email": u.get("email"),
                         "sections": p["sections"], "flags": {f: p[f] for f in P.FLAGS}, "invite_status": "accepted",
                         "access_status": acc, "access_label": STATUS_LABEL.get(acc, acc), "event_status": st,
                         "account_active": u.get("active", True), "org_access_active": m.get("active", True),
                         "last_login_at": u.get("last_login_at")})
        known = {(r_["email"] or "").lower() for r_ in rows}
        for inv in await db.org_invites.find({"org_id": org_id, "event_id": event_id, "status": {"$ne": "accepted"}}, {"_id": 0, "token": 0}).sort("created_at", -1).to_list(500):
            if inv["email"].lower() in known:
                continue
            known.add(inv["email"].lower())
            p = P.normalize_permissions(inv.get("permissions"), "collaboratore")
            ist = deps["invite_status"](inv)
            rows.append({"kind": "invite", "invite_id": inv["id"], "name": f"{inv.get('nome') or ''} {inv.get('cognome') or ''}".strip(),
                         "email": inv["email"], "sections": p["sections"], "flags": {f: p[f] for f in P.FLAGS},
                         "invite_status": ist, "access_status": "pending" if ist == "pending" else ist,
                         "access_label": {"pending": "Invito in attesa", "expired": "Invito scaduto", "revoked": "Invito revocato"}.get(ist, ist),
                         "expires_at": inv.get("expires_at"), "last_login_at": None})
        rows.sort(key=lambda x: (x["name"] or x["email"] or "").lower())
        return {"rows": rows, "sections": [{"key": k, "label": lbl} for k, lbl in P.SECTIONS if k not in P.HIDDEN_SECTIONS],
                "flags": P.FLAGS, "defaults": P.default_permissions("collaboratore"),
                "cap": None if cap.get("admin") else {"sections": cap.get("sections"), **{f: cap.get(f) for f in P.FLAGS}}}

    @r.post("/events/{event_id}/collaborators")
    async def invite_collab(event_id: str, body: CollabInviteIn, user: dict = Depends(require_admin)):
        org_id = user["org_id"]
        ev = await _event(org_id, event_id)
        cap = await _can_manage(user, event_id)
        email = body.email.lower()
        org = await deps["org_or_404"](org_id)
        eu = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
        m = await db.memberships.find_one({"user_id": eu["user_id"], "org_id": org_id}, {"_id": 0}) if eu else None
        if eu and eu.get("role") == "superadmin":
            raise HTTPException(status_code=400, detail="Questo indirizzo appartiene a un account della piattaforma")
        if m and m.get("role") != "collaboratore":
            raise HTTPException(status_code=409, detail="Questa persona è già Utente dell'organizzazione: ha già accesso secondo il suo ruolo")
        if m and m.get("active") is False:
            raise HTTPException(status_code=409, detail="L'accesso di questa persona all'organizzazione è disattivato: va riattivato prima di aggiungere eventi")
        # Anagrafica + presenza Staff dell'evento come Collaboratore (nessun duplicato per email)
        person = await db.persons.find_one({"org_id": org_id, "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0})
        if not person:
            person = {"id": new_id(), "org_id": org_id, "nome": body.nome.strip(), "cognome": body.cognome.strip(), "email": email,
                      "created_at": now_iso(), "provenienza": {"tipo": "invito_collaboratore", "at": now_iso(), "by": user.get("email"), "evento_id": event_id}}
            await db.persons.insert_one({**person})
        if not await db.staff.find_one({"org_id": org_id, "persona_id": person["id"], "evento_id": event_id}, {"_id": 1}):
            await db.staff.insert_one({"id": new_id(), "org_id": org_id, "persona_id": person["id"], "evento_id": event_id,
                                       "categoria": "collaboratore", "stato": "confermato", "created_at": now_iso()})
        if m:  # già Collaboratore attivo: si aggiunge l'evento, nessun nuovo account
            before = _perm(m)
            p = _apply(before, body, cap)
            p = await _set_event(m, event_id, None, user, perm=p)
            await audit(user, "collab_event_assigned", org_id=org_id, target_email=email, target_name=eu.get("name"),
                        detail=f"Evento «{ev['nome']}» · {_summary(p)}", meta={"event_id": event_id, "before": before, "after": p})
            return {"ok": True, "mode": "added"}
        prev = await db.org_invites.find_one({"org_id": org_id, "email": email, "status": "pending"}, {"_id": 0})
        evs = sorted(set(((prev or {}).get("permissions") or {}).get("events") or []) | {event_id}) if prev and isinstance(((prev.get("permissions") or {}).get("events")), list) else [event_id]
        p = _apply(P.default_permissions("collaboratore"), body, cap)
        p["events"] = evs
        inv = await deps["create_invite"](org, email, "collaboratore", user["user_id"], nome=body.nome, cognome=body.cognome)
        await db.org_invites.update_one({"id": inv["id"]}, {"$set": {"permissions": p, "persona_id": person["id"], "event_id": event_id}})
        await db.persons.update_one({"id": person["id"]}, {"$set": {"invite_status": "invito_inviato", "updated_at": now_iso()}})
        sent = await _send(inv, org)
        await audit(user, "collab_invited", org_id=org_id, target_email=email, target_name=f"{body.nome} {body.cognome}",
                    detail=f"Evento «{ev['nome']}» · {_summary(p)}", meta={"event_id": event_id, "after": p, "invite_id": inv["id"]})
        return {"ok": True, "mode": "invited", "email_sent": sent, "invite_id": inv["id"]}

    @r.put("/events/{event_id}/collaborators/{target_id}")
    async def edit_collab(event_id: str, target_id: str, body: PermIn, request: Request, user: dict = Depends(require_admin)):
        org_id = user["org_id"]
        ev = await _event(org_id, event_id)
        cap = await _can_manage(user, event_id)
        if target_id == user["user_id"]:
            raise HTTPException(status_code=400, detail="Non puoi modificare i tuoi permessi")
        if request.query_params.get("kind") == "invite":
            inv = await db.org_invites.find_one({"org_id": org_id, "id": target_id, "event_id": event_id}, {"_id": 0})
            if not inv:
                raise HTTPException(status_code=404, detail="Invito non trovato")
            before = P.normalize_permissions(inv.get("permissions"), "collaboratore")
            p = {**_apply(before, body, cap), "events": before["events"]}
            await db.org_invites.update_one({"id": target_id}, {"$set": {"permissions": p, "updated_at": now_iso()}})
            email, name = inv["email"], inv.get("nome")
        else:
            m = await db.memberships.find_one({"org_id": org_id, "user_id": target_id, "role": "collaboratore"}, {"_id": 0})
            if not m or not _event_status(m, event_id):
                raise HTTPException(status_code=404, detail="Collaboratore non trovato per questo evento")
            before = _perm(m)
            p = {**_apply(before, body, cap), "events": before["events"]}
            await db.memberships.update_one({"id": m["id"]}, {"$set": {"permissions": p, "updated_at": now_iso()}})
            tu = await db.users.find_one({"user_id": target_id}, {"_id": 0, "email": 1, "name": 1}) or {}
            email, name = tu.get("email"), tu.get("name")
        await audit(user, "collab_permissions_changed", org_id=org_id, target_email=email, target_name=name,
                    detail=f"Evento «{ev['nome']}» · Prima: {_summary(before)} → Dopo: {_summary(p)}",
                    meta={"event_id": event_id, "before": before, "after": p})
        return {"ok": True}

    @r.post("/events/{event_id}/collaborators/{target_id}/revoke")
    async def revoke_collab(event_id: str, target_id: str, request: Request, user: dict = Depends(require_admin)):
        org_id = user["org_id"]
        ev = await _event(org_id, event_id)
        await _can_manage(user, event_id)
        if request.query_params.get("kind") == "invite":
            inv = await db.org_invites.find_one({"org_id": org_id, "id": target_id, "event_id": event_id}, {"_id": 0})
            if not inv:
                raise HTTPException(status_code=404, detail="Invito non trovato")
            await db.org_invites.update_one({"id": target_id}, {"$set": {"status": "revoked", "updated_at": now_iso()}})
            await audit(user, "invite_revoked", org_id=org_id, target_email=inv["email"], detail=f"Invito collaboratore · evento «{ev['nome']}»")
            return {"ok": True}
        m = await db.memberships.find_one({"org_id": org_id, "user_id": target_id, "role": "collaboratore"}, {"_id": 0})
        if not m or _event_status(m, event_id) in (None, "revoked"):
            raise HTTPException(status_code=404, detail="Collaboratore non trovato per questo evento")
        before = _perm(m)
        p = await _set_event(m, event_id, "revoked", user)
        tu = await db.users.find_one({"user_id": target_id}, {"_id": 0, "email": 1, "name": 1}) or {}
        await audit(user, "collab_event_revoked", org_id=org_id, target_email=tu.get("email"), target_name=tu.get("name"),
                    detail=f"Accesso all'evento «{ev['nome']}» revocato", meta={"event_id": event_id, "before": before, "after": p})
        return {"ok": True}

    @r.post("/events/{event_id}/collaborators/{invite_id}/resend")
    async def resend_collab(event_id: str, invite_id: str, user: dict = Depends(require_admin)):
        await _can_manage(user, event_id)
        return await _resend(user, user["org_id"], invite_id, event_id)

    async def _resend(user: dict, org_id: str, invite_id: str, event_id: Optional[str] = None):
        q = {"org_id": org_id, "id": invite_id, **({"event_id": event_id} if event_id else {})}
        inv = await db.org_invites.find_one(q, {"_id": 0})
        if not inv or inv.get("status") == "accepted":
            raise HTTPException(status_code=404, detail="Invito non trovato")
        org = await deps["org_or_404"](org_id)
        token = secrets.token_urlsafe(32)
        await db.org_invites.update_one({"id": invite_id}, {"$set": {"token": token, "status": "pending", "updated_at": now_iso(),
                                        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}})
        sent = await _send({**inv, "token": token}, org)
        await audit(user, "invite_resent", org_id=org_id, target_email=inv["email"], detail="Invito collaboratore reinviato")
        return {"ok": True, "email_sent": sent}

    # ---------------- Super Admin: stato account e accessi ----------------
    async def _target(uid: str) -> dict:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Account non trovato")
        if u.get("role") == "superadmin":
            raise HTTPException(status_code=400, detail="Operazione non consentita sull'account Super Admin")
        return u

    async def _access(u: dict) -> dict:
        mems = await db.memberships.find({"user_id": u["user_id"]}, {"_id": 0}).to_list(200)
        orgs = {o["id"]: o for o in await db.organizations.find({"id": {"$in": [m["org_id"] for m in mems]}}, {"_id": 0, "id": 1, "nome": 1, "status": 1}).to_list(200)}
        out = []
        for m in mems:
            p = _perm(m)
            states = m.get("event_states") or {}
            ids = set(states) | (set(p["events"]) if p["events"] != "all" else set())
            names = {e["id"]: e for e in await db.events.find({"org_id": m["org_id"], "id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1}).to_list(2000)}
            evs = [{"id": e, "nome": (names.get(e) or {}).get("nome") or "Evento eliminato", "data_inizio": (names.get(e) or {}).get("data_inizio"),
                    "status": (states.get(e) or {}).get("status") or "active", "at": (states.get(e) or {}).get("at"),
                    "by": (states.get(e) or {}).get("by"), "reason": (states.get(e) or {}).get("reason")} for e in ids if e in names or e in states]
            evs.sort(key=lambda x: (x["nome"] or "").lower())
            o = orgs.get(m["org_id"]) or {}
            out.append({"org_id": m["org_id"], "org_nome": o.get("nome"), "org_disabled": o.get("status") == "disabled",
                        "role": m.get("role"), "role_label": P.ROLES.get(m.get("role"), m.get("role")),
                        "active": m.get("active", True), "deactivated_at": m.get("deactivated_at"), "deactivation_reason": m.get("deactivation_reason"),
                        "all_events": p["events"] == "all", "events": evs, "sections": p["sections"], "flags": {f: p[f] for f in P.FLAGS}})
        out.sort(key=lambda x: (x["org_nome"] or "").lower())
        invs = await db.org_invites.find({"email": (u.get("email") or "").lower(), "status": {"$ne": "accepted"}}, {"_id": 0, "token": 0}).to_list(100)
        return {"user_id": u["user_id"], "name": u.get("name"), "email": u.get("email"), "active": u.get("active", True),
                "deactivated_at": u.get("deactivated_at"), "deactivation_reason": u.get("deactivation_reason"), "reactivated_at": u.get("reactivated_at"),
                "last_login_at": u.get("last_login_at"), "memberships": out,
                "invites": [{"id": i["id"], "org_id": i["org_id"], "status": deps["invite_status"](i), "role": i.get("role"), "expires_at": i.get("expires_at")} for i in invs],
                "sections": [{"key": k, "label": lbl} for k, lbl in P.SECTIONS if k not in P.HIDDEN_SECTIONS], "flags": P.FLAGS}

    @r.get("/platform/users/{uid}/access")
    async def sa_access(uid: str, admin: dict = Depends(require_superadmin)):
        return await _access(await _target(uid))

    @r.post("/platform/users/{uid}/state")
    async def sa_state(uid: str, body: StateIn, admin: dict = Depends(require_superadmin)):
        u = await _target(uid)
        if body.active == u.get("active", True):
            return {"ok": True, "changed": False}
        acc = await _access(u)
        scope = "; ".join(f"{m['org_nome']}" + (f" ({', '.join(e['nome'] for e in m['events'] if e['status'] == 'active')})" if m["role"] == "collaboratore" and not m["all_events"] else "")
                          for m in acc["memberships"] if m["active"]) or "nessuna organizzazione attiva"
        if not body.active:
            blocking = await deps["blocking_admin_orgs"](uid)
            if blocking:
                raise HTTPException(status_code=400, detail=f"È l'unico Admin Organizzazione di: {', '.join(blocking)}. Assegna un altro Admin prima di disattivare l'account.")
            upd = {"active": False, "deactivated_at": now_iso(), "deactivation_reason": (body.reason or "").strip() or None, "deactivated_by": admin.get("email")}
            await db.user_sessions.delete_many({"user_id": uid})  # blocca subito le sessioni attive
        else:
            upd = {"active": True, "reactivated_at": now_iso(), "reactivated_by": admin.get("email")}
        await db.users.update_one({"user_id": uid}, {"$set": {**upd, "updated_at": now_iso()}})
        await audit(admin, "account_enabled" if body.active else "account_disabled", org_id=u.get("org_id"),
                    target_email=u.get("email"), target_name=u.get("name"),
                    detail=("Account riattivato · tornano accessibili: " if body.active else "Account disattivato · accessi sospesi: ") + scope
                    + (f" · motivo: {body.reason.strip()}" if body.reason and body.reason.strip() else ""),
                    meta={"target_user_id": uid, "orgs": [m["org_id"] for m in acc["memberships"]]})
        return {"ok": True, "changed": True}

    async def _membership(uid: str, org_id: str) -> dict:
        m = await db.memberships.find_one({"user_id": uid, "org_id": org_id}, {"_id": 0})
        if not m:
            raise HTTPException(status_code=404, detail="Associazione non trovata")
        return m

    @r.post("/platform/users/{uid}/memberships/{org_id}/state")
    async def sa_membership_state(uid: str, org_id: str, body: StateIn, admin: dict = Depends(require_superadmin)):
        u = await _target(uid)
        m = await _membership(uid, org_id)
        if body.active == m.get("active", True):
            return {"ok": True, "changed": False}
        org = await deps["org_or_404"](org_id)
        if not body.active and m.get("role") == "admin_org":
            await deps["guard_last_admin"](org, uid)
        if body.active:
            await deps["check_limit"](org_id, "users")
        upd = {"active": body.active, "updated_at": now_iso()}
        upd.update({"deactivated_at": now_iso(), "deactivation_reason": (body.reason or "").strip() or None} if not body.active else {"reactivated_at": now_iso()})
        await db.memberships.update_one({"id": m["id"]}, {"$set": upd})
        await audit(admin, "member_enabled" if body.active else "member_disabled", org_id=org_id, org_name=org.get("nome"),
                    target_email=u.get("email"), target_name=u.get("name"),
                    detail=f"Accesso all'organizzazione {'riattivato' if body.active else 'disattivato'} dal Super Admin" + (f" · motivo: {body.reason.strip()}" if body.reason and body.reason.strip() else ""))
        return {"ok": True, "changed": True}

    @r.post("/platform/users/{uid}/memberships/{org_id}/events/{eid}")
    async def sa_event(uid: str, org_id: str, eid: str, body: EventActionIn, admin: dict = Depends(require_superadmin)):
        u = await _target(uid)
        m = await _membership(uid, org_id)
        if m.get("role") != "collaboratore":
            raise HTTPException(status_code=400, detail="La gestione per evento vale solo per i Collaboratori")
        ev = await _event(org_id, eid)
        cur = _event_status(m, eid)
        before = _perm(m)
        if body.action == "disable" and cur == "active":
            p = await _set_event(m, eid, "disabled", admin, body.reason)
            act, txt = "collab_event_disabled", "disattivato"
        elif body.action == "restore" and cur == "disabled":
            p = await _set_event(m, eid, None, admin)
            act, txt = "collab_event_restored", "ripristinato con i permessi precedenti"
        elif body.action == "revoke" and cur in ("active", "disabled"):
            p = await _set_event(m, eid, "revoked", admin, body.reason)
            act, txt = "collab_event_revoked", "revocato"
        elif body.action == "assign" and cur in (None, "revoked"):
            if body.sections is None:
                raise HTTPException(status_code=400, detail="Per riassegnare un accesso revocato scegli esplicitamente i permessi")
            p = await _set_event(m, eid, None, admin, perm=_apply(before, body))
            act, txt = "collab_event_assigned", "riassegnato"
        else:
            raise HTTPException(status_code=400, detail="Operazione non disponibile per lo stato attuale dell'accesso")
        await audit(admin, act, org_id=org_id, target_email=u.get("email"), target_name=u.get("name"),
                    detail=f"Accesso all'evento «{ev['nome']}» {txt}" + (f" · Prima: {_summary(before)} → Dopo: {_summary(p)}" if act == "collab_event_assigned" else "")
                    + (f" · motivo: {body.reason.strip()}" if body.reason and body.reason.strip() else ""),
                    meta={"event_id": eid, "before": before, "after": p, "target_user_id": uid})
        return {"ok": True, "status": _event_status({**m, "permissions": p, "event_states": (await _membership(uid, org_id)).get("event_states")}, eid)}

    @r.put("/platform/users/{uid}/memberships/{org_id}/permissions")
    async def sa_perms(uid: str, org_id: str, body: PermIn, admin: dict = Depends(require_superadmin)):
        u = await _target(uid)
        m = await _membership(uid, org_id)
        if m.get("role") == "admin_org":
            raise HTTPException(status_code=400, detail="L'Admin Organizzatore ha accesso completo")
        before = _perm(m)
        p = {**_apply(before, body), "events": before["events"]}
        p = P.normalize_permissions(p, m.get("role") or "user")
        await db.memberships.update_one({"id": m["id"]}, {"$set": {"permissions": p, "updated_at": now_iso()}})
        await audit(admin, "permissions_changed", org_id=org_id, target_email=u.get("email"), target_name=u.get("name"),
                    detail=f"Super Admin · Prima: {_summary(before)} → Dopo: {_summary(p)}", meta={"before": before, "after": p, "target_user_id": uid})
        return {"ok": True}

    @r.post("/platform/users/{uid}/invites/{invite_id}/resend")
    async def sa_resend(uid: str, invite_id: str, admin: dict = Depends(require_superadmin)):
        inv = await db.org_invites.find_one({"id": invite_id}, {"_id": 0, "org_id": 1})
        if not inv:
            raise HTTPException(status_code=404, detail="Invito non trovato")
        return await _resend(admin, inv["org_id"], invite_id)

    return {"router": r}
