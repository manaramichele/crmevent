# requirements.txt — regola per il deploy Aruba (GitHub Actions)
- NON includere la riga `litellm @ https://customer-assets.emergentagent.com/...whl#sha256=...` in backend/requirements.txt.
  `pip freeze` la reinserisce: rimuoverla sempre dopo ogni freeze.
- Causa (2026-11-14): emergentintegrations==0.2.1 dichiara `litellm @ <URL senza hash>`; la riga di freeze ha lo stesso URL con `#sha256=`.
  pip li considera due requisiti diretti diversi → "Cannot install emergentintegrations==0.2.1 and litellm 1.80.0 ... ResolutionImpossible".
- litellm resta installato comunque come dipendenza di emergentintegrations (usato da support_service, social_ai, social_creative, press, news, cal_reverse).
- Verifica: python3.11 -m venv /tmp/v && /tmp/v/bin/pip install -r backend/requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ && /tmp/v/bin/pip check
