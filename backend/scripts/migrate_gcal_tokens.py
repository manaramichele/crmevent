"""Migrazione idempotente dei token Google Calendar in chiaro → AES-256-GCM (calendar_connections.tokens → tokens_enc).

Uso (dal server, nella cartella backend con il .env di produzione):
  python scripts/migrate_gcal_tokens.py                      # DRY-RUN: solo conteggi, nessuna modifica
  python scripts/migrate_gcal_tokens.py --backup /root/gcal_backup.json   # backup (permessi 600) dei record in chiaro
  python scripts/migrate_gcal_tokens.py --apply --backup /root/gcal_backup.json
Non stampa mai token. Un record viene modificato solo dopo aver verificato che la decifratura restituisca gli stessi token.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import gcal_tokens  # noqa: E402


async def main(apply: bool, backup: str | None, db=None):
    db = db if db is not None else AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    if not gcal_tokens.key_configured():
        print("ERRORE: GOOGLE_TOKEN_ENCRYPTION_KEY mancante o non valida. Nessuna modifica.")
        return {"error": "key_missing"}
    total = await db.calendar_connections.count_documents({})
    enc = await db.calendar_connections.count_documents({"tokens_enc": {"$exists": True}})
    plain = await db.calendar_connections.find({"tokens": {"$exists": True}, "tokens_enc": {"$exists": False}}, {"_id": 0}).to_list(100000)
    print(f"Connessioni totali: {total} | gi\u00e0 cifrate: {enc} | in chiaro da migrare: {len(plain)}")
    if backup and plain:
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(plain, f, default=str)
        print(f"Backup scritto ({len(plain)} record, permessi 600): {backup} \u2014 cancellalo dopo la verifica.")
    if not apply:
        print("DRY-RUN: nessuna modifica. Riesegui con --apply per cifrare.")
        return {"total": total, "encrypted": enc, "plain": len(plain), "migrated": 0}
    if plain and not backup:
        print("ERRORE: --apply richiede --backup. Nessuna modifica.")
        return {"error": "backup_required"}
    ok = failed = 0
    for c in plain:
        try:
            e = gcal_tokens.encrypt(c["tokens"])
            if gcal_tokens.decrypt(e) != c["tokens"]:
                raise ValueError("verifica")
            res = await db.calendar_connections.update_one({"user_id": c["user_id"], "tokens_enc": {"$exists": False}},
                                                           {"$set": {"tokens_enc": e}, "$unset": {"tokens": ""}})
            ok += res.modified_count
        except Exception as ex:  # noqa: BLE001
            failed += 1
            print(f"Record non migrato (user {c.get('user_id', '?')[:6]}\u2026): {type(ex).__name__}")
    print(f"Migrati: {ok} | non migrati: {failed}")
    return {"total": total, "encrypted": enc, "plain": len(plain), "migrated": ok, "failed": failed}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--backup")
    a = p.parse_args()
    asyncio.run(main(a.apply, a.backup))
