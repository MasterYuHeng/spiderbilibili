from __future__ import annotations

import json

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from _backend_bootstrap import BACKEND_DIR


def main() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    script_dir = ScriptDirectory.from_config(config)
    heads = sorted(script_dir.get_heads())
    current: list[str] = []

    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        if inspect(connection).has_table("alembic_version"):
            rows = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchall()
            current = sorted(str(row[0]) for row in rows if row and row[0])

    print(json.dumps({"current": current, "heads": heads}))


if __name__ == "__main__":
    main()
