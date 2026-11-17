# ruff: noqa: F811
# Control Room Phase 3 retest (iteration 171): mobile auto-step, backward actions without side effects, close->completata, coord sector move, health 404, coordinatori notification
import uuid
import requests
from test_controlroom_phase3_itv import A, C, W, OPS, MB, new_itv, st, itv, state, res_state  # noqa


def act(W, iid, action, note=None):
    return requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": action, "note": note})


def diary_count(A, iid):
    return len(A.get(f"{OPS}/diary", params={"intervention_id": iid}).json()["rows"])


# auto-step: partito on segnalato after central radio confirm
def test_partito_autostep_after_radio_confirm(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    assert A.post(f"{OPS}/interventions/{iid}/assignments/{W['R1']}/confirm", json={"via": "radio"}).status_code == 200
    r = act(W, iid, "partito")
    assert r.status_code == 200, r.text
    it = itv(A, iid)
    assert it["stato"] == "squadra_inviata"
    assert it.get("t_presa") and it.get("t_invio")
    tos = [h["to"] for h in it["history"]]
    assert tos == ["preso_in_carico", "squadra_inviata"], tos


# auto-step: risolto directly from segnalato with non_confermata asg
def test_risolto_autostep_from_segnalato(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    r = act(W, iid, "risolto")
    assert r.status_code == 200, r.text
    it = itv(A, iid)
    assert it["stato"] == "risolto"
    assert [h["to"] for h in it["history"]] == ["preso_in_carico", "squadra_inviata", "sul_posto", "risolto"]
    assert it["assignments"][0]["stato"] == "confermata"


# auto-step from in_attesa
def test_arrivato_from_in_attesa(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    assert st(A, iid, "in_attesa").status_code == 200
    r = act(W, iid, "arrivato")
    assert r.status_code == 200, r.text
    assert itv(A, iid)["stato"] == "sul_posto"


# backward action -> 409 without side effects
def test_backward_action_no_side_effects(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    for to in ("preso_in_carico", "squadra_inviata", "sul_posto"):
        assert st(A, iid, to).status_code == 200
    before = diary_count(A, iid)
    v0 = itv(A, iid)["version"]
    for a in ("partito", "arrivato"):
        r = act(W, iid, a)
        assert r.status_code == 409, f"{a}: {r.status_code} {r.text}"
    it = itv(A, iid)
    assert it["assignments"][0]["stato"] == "non_confermata"
    assert it["version"] == v0
    assert diary_count(A, iid) == before
    # conferma still allowed on sul_posto (just confirms)
    assert act(W, iid, "conferma").status_code == 200
    assert itv(A, iid)["assignments"][0]["stato"] == "confermata"
    assert itv(A, iid)["stato"] == "sul_posto"


# risolto twice -> 409
def test_repeat_risolto_409(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    assert act(W, iid, "risolto").status_code == 200
    assert act(W, iid, "risolto").status_code == 409


# closing/annulling -> asg completata; reopen -> senza_squadra True, resource disponibile
def test_close_sets_completata_and_reopen_consistent(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R4"]]})
    assert res_state(A, W["R4"])["stato"] == "impegnato"
    assert st(A, iid, "annullato", motivo="TEST_ x").status_code == 200
    it = itv(A, iid)
    assert [a["stato"] for a in it["assignments"]] == ["completata"]
    assert res_state(A, W["R4"])["stato"] == "disponibile"
    assert st(A, iid, "segnalato", motivo="TEST_ riapro").status_code == 200
    it = itv(A, iid)
    assert it["senza_squadra"] is True and it["attesa_conferma"] is False
    # can reassign after reopen
    r = A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R4"]]})
    assert r.status_code == 200, r.text
    assert res_state(A, W["R4"])["stato"] == "impegnato"
    st(A, iid, "annullato", motivo="TEST_ cleanup")


# mobile action on closed intervention -> 409 (expected) not 403
def test_mobile_action_on_closed_is_409(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    assert act(W, iid, "risolto").status_code == 200
    assert st(A, iid, "chiuso").status_code == 200
    r = act(W, iid, "aggiorna", "x")
    print("action on closed:", r.status_code, r.text[:120])
    assert r.status_code == 409, f"{r.status_code} {r.text}"


# coord scoped S1 cannot move to S2 via PUT
def test_coord_cannot_move_sector(A, C, W):
    c = next(m for m in A.get(f"{OPS}/members").json()["members"] if m["email"] == "test_cr_c@crmevent-test.it")
    prev = (c["cr_role"], c["sector_ids"])
    try:
        A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": "coordinatore", "sector_ids": [W["S1"]]})
        ic = new_itv(C, W).json()["id"]
        it = itv(C, ic)
        base = {"tipologia": "sanitario", "priorita": "alta", "descrizione": "TEST_P3 moved", "version": it["version"]}
        assert C.put(f"{OPS}/interventions/{ic}", json={**base, "km": 15}).status_code == 403
        assert C.put(f"{OPS}/interventions/{ic}", json={**base, "sector_id": W["S2"]}).status_code == 403
        assert itv(A, ic)["sector_id"] == W["S1"]
        # in-sector edit still OK
        r = C.put(f"{OPS}/interventions/{ic}", json={**base, "km": 5, "descrizione": "TEST_P3 in S1"})
        assert r.status_code == 200, r.text
        assert itv(A, ic)["descrizione"] == "TEST_P3 in S1"
    finally:
        A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": prev[0], "sector_ids": prev[1]})


# health on unknown iid -> 404
def test_health_unknown_404(A, W):
    assert A.get(f"{OPS}/interventions/{uuid.uuid4().hex}/health").status_code == 404
    assert A.post(f"{OPS}/interventions/{uuid.uuid4().hex}/health", json={"text": "x"}).status_code == 404


# coordinatori message creates a centrale notification
def test_coordinatori_message_centrale_notif(A, W):
    txt = f"TEST_coord {uuid.uuid4().hex[:6]}"
    r = A.post(f"{OPS}/messages", json={"to_type": "coordinatori", "text": txt})
    assert r.status_code == 200, r.text
    notifs = state(A)["notifications"]
    assert any(txt in n["text"] for n in notifs), [n["text"] for n in notifs[:5]]
