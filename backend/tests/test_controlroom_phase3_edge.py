# Control Room Phase 3 edge cases: coordinatore edit scope, reopen by coordinatore, cross-org mobile token, reopen assignment consistency
import requests, pytest
from test_controlroom_phase3_itv import A, C, W, _login, OPS, MB, API, new_itv, st, itv, state, res_state  # noqa


def test_coord_edit_cannot_move_out_of_sector(A, C, W):
    c = next(m for m in A.get(f"{OPS}/members").json()["members"] if m["email"] == "test_cr_c@crmevent-test.it")
    prev = c["cr_role"]
    try:
        A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": "coordinatore", "sector_ids": [W["S1"]]})
        ic = new_itv(C, W).json()["id"]
        it = itv(C, ic)
        body = {"tipologia": "sanitario", "priorita": "alta", "descrizione": "TEST_P3 moved", "km": 15, "version": it["version"]}
        r = C.put(f"{OPS}/interventions/{ic}", json=body)
        print("coord edit to S2:", r.status_code, itv(A, ic)["sector_id"] == W["S2"])
        # reopen by coordinatore
        ia = new_itv(A, W).json()["id"]
        st(A, ia, "annullato", motivo="x")
        r2 = st(C, ia, "preso_in_carico", motivo="riapro")
        print("coord reopen:", r2.status_code)
        assert r2.status_code == 403
        assert r.status_code == 403, "coordinatore moved intervention outside own sector"
    finally:
        A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": prev, "sector_ids": c["sector_ids"]})


def test_reopen_assignment_consistency(A, W):
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R4"]]})
    assert res_state(A, W["R4"])["stato"] == "impegnato"
    st(A, iid, "annullato", motivo="x")
    assert res_state(A, W["R4"])["stato"] == "disponibile"
    st(A, iid, "segnalato", motivo="riapro")
    it = itv(A, iid)
    print("after reopen: asg", [a["stato"] for a in it["assignments"]], "senza_squadra", it["senza_squadra"], "res", res_state(A, W["R4"])["stato"])


def test_cross_org_mobile_token(A, W):
    B = _login("test_cr_b@crmevent-test.it")
    evs = B.get(f"{API}/controlroom/events").json()
    evs = evs.get("events", evs) if isinstance(evs, dict) else evs
    ev = next((e for e in evs if B.get(f"{API}/controlroom/events/{e['id']}/ops").status_code == 200), None)
    if not ev:
        pytest.skip("org B has no active CR event")
    ops_b = f"{API}/controlroom/events/{ev['id']}/ops"
    rid = B.post(f"{ops_b}/resources", json={"kind": "persona", "nome": "TEST_P3 B op"}).json()["id"]
    try:
        inv = B.post(f"{ops_b}/invites", json={"resource_id": rid}).json()
        tok = inv["token"]
        a_itv = W["itvs"][0]
        r = requests.post(f"{MB}/{tok}/interventions/{a_itv}/action", json={"action": "conferma"})
        r2 = requests.post(f"{MB}/{tok}/interventions/{a_itv}/photo", files={"file": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 10, "image/png")})
        home = requests.get(f"{MB}/{tok}").json()
        print("cross-org action", r.status_code, "photo", r2.status_code, "home itvs", len(home["interventions"]))
        assert r.status_code == 404 and r2.status_code == 404
        assert all(i["id"] != a_itv for i in home["interventions"])
        B.delete(f"{ops_b}/invites/{inv['id']}")
    finally:
        B.delete(f"{ops_b}/resources/{rid}")


def test_partito_after_central_confirm_on_segnalato(A, W):
    """Centrale confirms via radio while the intervention is still SEGNALATO -> the mobile CONFERMA button is hidden; PARTITO should still work."""
    iid = new_itv(A, W).json()["id"]
    A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
    A.post(f"{OPS}/interventions/{iid}/assignments/{W['R1']}/confirm", json={"via": "radio"})
    r = requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": "partito"})
    print("partito after radio confirm:", r.status_code, r.text[:120])
    assert r.status_code == 200
