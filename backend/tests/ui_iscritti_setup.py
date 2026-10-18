# UI setup for Elenco Iscritti tests: verifies the existing TEST_ISCR org, writes CSV for the wizard,
# and registers an inactive org (to check the sidebar entry is hidden). Prints emails for cleanup.
import time
import requests

URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/") + "/api"
email = open("/tmp/iscr_email").read().strip()
s = requests.Session()
print("login", s.post(f"{URL}/auth/login", json={"email": email, "password": "Password123!"}).status_code)
print("status", s.get(f"{URL}/iscritti/status").json().get("active"))
eds = s.get(f"{URL}/iscritti/edizioni").json()
print("edizioni", [(e["event_nome"], e["anno"], e["edizione"], e["iscritti"]) for e in eds["edizioni"]])
print("total", s.get(f"{URL}/iscritti").json()["total"])
open("/tmp/ui_iscritti.csv", "w").write("First Name;Last Name;E-mail;Race;Newsletter;Shoe\nUi;Uno;ui.uno.test@example.com;10K;si;42\nUi;Due;ui.due.test@example.com;10K;no;40\n;;bad;;;\n")
ts = str(int(time.time()))
e2 = f"test_iscrinactive_{ts}@example.com"
r = requests.post(f"{URL}/auth/register-organization", json={"nome": "Test", "cognome": "Inactive", "email": e2, "password": "Password123!",
                                                           "org_name": f"TEST_ISCR Inactive {ts}", "telefono": "+393331234567", "accept_terms": True})
print("inactive org", r.status_code, e2)
open("/tmp/iscr_inactive_email", "w").write(e2)
