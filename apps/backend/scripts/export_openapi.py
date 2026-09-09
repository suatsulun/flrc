import json
from pathlib import Path

from flrc.config import settings
from flrc.main import create_app

# The contract documents every route the product can serve. Demo-only routes
# are mounted solely under ENV=demo, so the export uses that profile.
settings.env = "demo"

out = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json"
out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
print(f"wrote {out}")
