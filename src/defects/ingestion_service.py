from dataclasses import replace
from typing import Any, Dict

from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.allure import parse_allure
from src.ingest.cucumber import parse_cucumber
from src.ingest.cypress import parse_cypress
from src.ingest.detect import detect_source
from src.ingest.junit import parse_junit
from src.ingest.playwright import parse_playwright
from src.ingest.robot import parse_robot
from src.ingest.testng import parse_testng
from src.sanitizer import sanitize_text

_PARSERS = {
    "allure": parse_allure,
    "junit": parse_junit,
    "testng": parse_testng,
    "cucumber": parse_cucumber,
    "playwright": parse_playwright,
    "cypress": parse_cypress,
    "robot": parse_robot,
}


class IngestionService:
    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder):
        self.repo = repo
        self.embedder = embedder

    def ingest_report(
        self,
        *,
        user_id: str,
        org_id: str,
        project: str,
        source: str,
        data: bytes,
    ) -> Dict[str, Any]:
        if source == "auto":
            detected = detect_source(data)
            if detected is None:
                raise ValueError(
                    "no se reconoció el formato; selecciónalo manualmente"
                )
            source = detected
        parser = _PARSERS.get(source)
        if parser is None:
            raise ValueError(f"unsupported source: {source}")
        records = parser(data, project=project)
        items = []
        for rec in records:
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            embedding = self.embedder.embed(f"{clean.error_type or ''} {message}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=embedding))
        return self.repo.ingest_run(
            user_id=user_id, org_id=org_id, project=project, source=source, items=items
        )
