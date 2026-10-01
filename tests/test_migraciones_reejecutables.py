"""Las migraciones tienen que poder aplicarse dos veces.

scripts/docker_init.py re-aplica TODAS en cada arranque de la demo con Docker:
un `create policy` sin su `drop policy if exists` previo hace fallar el segundo
arranque con «policy already exists». Test estático: no necesita BD.
"""
import re
from pathlib import Path

_MIGRATIONS = sorted((Path(__file__).resolve().parent.parent / "db" / "migrations").glob("*.sql"))
_CREATE = re.compile(r"create\s+policy\s+(\w+)\s+on\s+([\w.]+)", re.I)


def test_every_create_policy_is_preceded_by_its_drop():
    faltan = []
    for path in _MIGRATIONS:
        sql = path.read_text()
        for m in _CREATE.finditer(sql):
            name, table = m.group(1), m.group(2)
            drop = re.compile(rf"drop\s+policy\s+if\s+exists\s+{name}\s+on\s+{re.escape(table)}", re.I)
            if not drop.search(sql[:m.start()]):
                faltan.append(f"{path.name}: {name} on {table}")
    assert not faltan, "create policy sin drop previo: " + ", ".join(faltan)
