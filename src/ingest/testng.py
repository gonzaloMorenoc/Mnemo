from typing import List
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

from src.ingest.models import (
    FailureRecord,
    int_attr,
    parse_error_type,
    strip_ansi,
    strip_ansi_bytes,
    synthetic_failure_record,
)


def parse_testng(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un testng-results.xml; devuelve los test-method FAIL, INCLUIDOS los
    métodos de configuración (@BeforeMethod/@BeforeSuite) que fallan — un setup roto
    es un fallo real que deja los tests en SKIP y no debe pasar como run verde."""
    data = strip_ansi_bytes(data)
    try:
        root = ET.fromstring(data)
    except (ParseError, DefusedXmlException) as exc:
        raise ValueError(f"Invalid or unsafe TestNG XML: {exc}") from exc
    records: List[FailureRecord] = []
    for cls in root.iter("class"):
        classname = cls.get("name") or ""
        for tm in cls.findall("test-method"):
            if (tm.get("status") or "").upper() != "FAIL":
                continue
            is_config = (tm.get("is-config") or "").lower() == "true"
            name = tm.get("name") or "unknown"
            if is_config:
                name = f"{name} (config)"
            full = f"{classname}.{name}" if classname else name
            exc_node = tm.find("exception")
            error_type = exc_node.get("class") if exc_node is not None else None
            message = ""
            trace = None
            if exc_node is not None:
                msg_node = exc_node.find("message")
                if msg_node is not None and msg_node.text:
                    message = strip_ansi(msg_node.text.strip())
                st_node = exc_node.find("full-stacktrace")
                if st_node is not None and st_node.text:
                    trace = strip_ansi(st_node.text.strip()) or None
            if not error_type:
                error_type = parse_error_type(message)
            records.append(
                FailureRecord(
                    test_name=full,
                    error_type=error_type,
                    message=message,
                    trace=trace,
                    project=project,
                    source="testng",
                )
            )

    # Red de seguridad: la cabecera declara fallos pero no se extrajo ninguno.
    if not records:
        declared = int_attr(root, "failed")
        if declared > 0:
            records.append(synthetic_failure_record(project=project, source="testng", declared=declared))
    return records
