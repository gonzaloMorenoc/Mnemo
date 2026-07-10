import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import (
    FailureRecord,
    int_attr,
    parse_error_type,
    strip_ansi,
    strip_ansi_bytes,
    synthetic_failure_record,
)


def _fail_msgs(node) -> List[str]:
    return [
        strip_ansi(m.text.strip())
        for m in node.iter("msg")
        if (m.get("level") or "").upper() == "FAIL" and m.text
    ]


def parse_robot(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un output.xml de Robot Framework; devuelve tests FAIL, fallos de
    Suite Setup/Teardown (que no aparecen como <test>), y una red de seguridad."""
    data = strip_ansi_bytes(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid Robot XML: {exc}") from exc
    records: List[FailureRecord] = []
    for test in root.iter("test"):
        status = test.find("status")
        if status is None or (status.get("status") or "").upper() != "FAIL":
            continue
        message = strip_ansi((status.text or "").strip())
        fail_msgs = _fail_msgs(test)
        if not message and fail_msgs:
            message = fail_msgs[-1]
        trace = "\n".join(fail_msgs) or None
        records.append(
            FailureRecord(
                test_name=test.get("name") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="robot",
            )
        )

    # Fallos de Suite Setup/Teardown: un teardown que falla tras tests en PASS deja
    # el suite FAIL sin ningún <test> fallido → se perdería el fallo por completo.
    for suite in root.iter("suite"):
        for kw in suite.findall("kw"):
            if (kw.get("type") or "").lower() not in ("setup", "teardown"):
                continue
            status = kw.find("status")
            if status is None or (status.get("status") or "").upper() != "FAIL":
                continue
            fail_msgs = _fail_msgs(kw)
            message = strip_ansi((status.text or "").strip()) or (fail_msgs[-1] if fail_msgs else "")
            kind = (kw.get("type") or "setup").lower()
            records.append(
                FailureRecord(
                    test_name=f"{suite.get('name') or 'suite'} (suite {kind})",
                    error_type=parse_error_type(message),
                    message=message or f"Suite {kind} failed (sin mensaje)",
                    trace="\n".join(fail_msgs) or None,
                    project=project,
                    source="robot",
                )
            )

    # Red de seguridad: las estadísticas declaran fallos pero no se extrajo ninguno.
    if not records:
        declared = max((int_attr(s, "fail") for s in root.iter("stat")), default=0)
        if declared > 0:
            records.append(synthetic_failure_record(project=project, source="robot", declared=declared))
    return records
