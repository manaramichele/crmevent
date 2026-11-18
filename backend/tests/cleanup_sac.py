import os, requests
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
NOVA = "d91c8d145b8b454ca09962d9d43fcc12"
s = requests.Session()
s.post(f"{B}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
H = {"X-Org-Id": NOVA}
print("del quota", s.delete(f"{B}/api/asd/quote/701656a19e624abfa9855c2e226b2993", headers=H).status_code)
print("del socio", s.delete(f"{B}/api/asd/soci/44b1d019e75d476c8dacd3f9f853104b", headers=H).status_code)
soci = s.get(f"{B}/api/asd/soci", headers=H).json()
print("remaining soci Nova", [x.get("cognome") for x in (soci if isinstance(soci, list) else soci.get("items", []))])
oid = "25dfb358b0bd472ca48c87336f9b711e"
o = next((x for x in s.get(f"{B}/api/platform/organizations").json() if x["id"] == oid), None)
if o:
    print("del org", s.delete(f"{B}/api/platform/organizations/{oid}", json={"confirm_name": o["nome"]}).status_code)
users = s.get(f"{B}/api/platform/users").json()
users = users if isinstance(users, list) else users.get("items", users.get("users", []))
for u in users:
    if u.get("email", "").startswith(("test_sac_353abdf3", "test_sac_ui_0b8ed7")):
        print("del user", u["email"], s.delete(f"{B}/api/platform/users/{u['user_id']}").status_code)
print("TEST_SAC orgs left", [x["nome"] for x in s.get(f"{B}/api/platform/organizations").json() if x["nome"].startswith("TEST_SAC")])
