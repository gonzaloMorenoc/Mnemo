import json
from typing import Optional
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def detect_source(data: bytes, filename: Optional[str] = None) -> Optional[str]:
    """Detecta el formato de un reporte por su contenido. Devuelve el `source` o None.

    El orden de las reglas resuelve los solapamientos (XML vs JSON, y dentro de JSON
    playwright/cypress comparten 'stats', cucumber/allure pueden ser listas).
    """
    # 1) XML por root tag
    try:
        root = ET.fromstring(data)
    except (ParseError, DefusedXmlException):
        root = None
    if root is not None:
        tag = _localname(root.tag)
        if tag == "testng-results":
            return "testng"
        if tag == "robot":
            return "robot"
        if tag in ("testsuite", "testsuites"):
            return "junit"
        return None
    # 2) JSON por estructura
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict):
        if "suites" in obj and "stats" in obj:
            return "playwright"
        if "results" in obj and "stats" in obj:
            return "cypress"
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "elements" in obj[0]:
        return "cucumber"
    items = obj if isinstance(obj, list) else [obj]
    if items and isinstance(items[0], dict):
        first = items[0]
        if "statusDetails" in first or (
            "status" in first and ("uuid" in first or "fullName" in first)
        ):
            return "allure"
    return None
