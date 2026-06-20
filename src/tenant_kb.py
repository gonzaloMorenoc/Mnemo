import io
import json
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DATABASE_URL,
    DEFAULT_TOP_K,
    EMBEDDING_MODEL,
    UPLOAD_DIR,
)
from src.sanitizer import build_provenance_metadata, sanitize_text
from src.scope_priority import SCOPE_PRIORITY, prioritize_scoped_results


ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".log", ".md", ".json", ".pdf", ".zip"}


@dataclass
class IngestionResult:
    document_id: str
    chunk_count: int
    global_document_id: Optional[str]
    storage_path: str


class TenantKBRepository:
    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for multi-tenant KB endpoints")
        self.db_url = db_url
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

    def _connect(self):
        conn = psycopg.connect(self.db_url, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _set_user_claims(self, conn: psycopg.Connection, user_id: str):
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def create_organization(self, *, user_id: str, name: str) -> Dict[str, Any]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.organizations (name, created_by)
                    values (%s, %s)
                    returning id, name, join_code, created_at
                    """,
                    (name.strip(), user_id),
                )
                organization = cur.fetchone()
            conn.commit()
        return organization

    def join_organization(self, *, user_id: str, join_code: str) -> Dict[str, Any]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select public.join_organization_by_code(%s) as org_id", (join_code.strip(),))
                row = cur.fetchone()
                if not row or not row.get("org_id"):
                    raise ValueError("Could not join organization with the provided code")
                cur.execute(
                    """
                    select o.id, o.name, o.join_code, m.role
                    from public.organizations o
                    join public.memberships m on m.org_id = o.id
                    where o.id = %s and m.user_id = %s
                    """,
                    (row["org_id"], user_id),
                )
                organization = cur.fetchone()
            conn.commit()
        return organization

    def list_user_organizations(self, *, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select o.id, o.name, o.join_code, m.role, o.created_at
                    from public.memberships m
                    join public.organizations o on o.id = m.org_id
                    where m.user_id = %s
                    order by o.created_at desc
                    """,
                    (user_id,),
                )
                return cur.fetchall()

    def _is_org_member(self, cur: psycopg.Cursor, *, user_id: str, org_id: str) -> bool:
        cur.execute(
            """
            select exists(
                select 1
                from public.memberships
                where org_id = %s and user_id = %s
            ) as is_member
            """,
            (org_id, user_id),
        )
        result = cur.fetchone()
        return bool(result and result["is_member"])

    def _read_pdf_text(self, data: bytes) -> str:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()

    def _extract_text_entries(self, filename: str, data: bytes) -> List[Dict[str, str]]:
        extension = os.path.splitext(filename)[1].lower()
        if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {extension}")

        if extension == ".zip":
            entries: List[Dict[str, str]] = []
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    nested_ext = os.path.splitext(item.filename)[1].lower()
                    if nested_ext not in {".txt", ".log", ".md", ".json"}:
                        continue
                    payload = archive.read(item)
                    entries.extend(self._extract_text_entries(item.filename, payload))
            if not entries:
                raise ValueError("No supported files found inside zip")
            return entries

        if extension == ".json":
            parsed = json.loads(data.decode("utf-8", errors="replace"))
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
            return [{"title": filename, "text": text}]

        if extension == ".pdf":
            return [{"title": filename, "text": self._read_pdf_text(data)}]

        return [{"title": filename, "text": data.decode("utf-8", errors="replace")}]

    def _persist_upload_file(self, *, user_id: str, filename: str, data: bytes) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        user_dir = os.path.join(UPLOAD_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        destination = os.path.join(user_dir, stored_name)
        with open(destination, "wb") as handle:
            handle.write(data)
        return destination

    def _insert_document(
        self,
        cur: psycopg.Cursor,
        *,
        title: str,
        mime_type: Optional[str],
        source_type: str,
        scope: str,
        owner_user_id: Optional[str],
        org_id: Optional[str],
        storage_path: Optional[str],
        contributed_to_global: bool,
    ) -> str:
        cur.execute(
            """
            insert into public.documents (
                title, mime_type, source_type, scope, owner_user_id, org_id, storage_path, contributed_to_global
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                title,
                mime_type,
                source_type,
                scope,
                owner_user_id,
                org_id,
                storage_path,
                contributed_to_global,
            ),
        )
        row = cur.fetchone()
        return str(row["id"])

    def _insert_chunks_and_embeddings(
        self,
        cur: psycopg.Cursor,
        *,
        document_id: str,
        chunks: Sequence[str],
        scope: str,
        owner_user_id: Optional[str],
        org_id: Optional[str],
        force_sanitized: bool = False,
    ):
        embeddings = self.embeddings.embed_documents(list(chunks))
        for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_for_storage = sanitize_text(chunk_text) if force_sanitized else chunk_text
            metadata = build_provenance_metadata(chunk_for_storage)
            sanitized_value = sanitize_text(chunk_text) if (force_sanitized or scope == "global") else None
            cur.execute(
                """
                insert into public.chunks (
                    document_id, chunk_index, content, sanitized_content, scope, owner_user_id, org_id, tech_tags, error_type
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    document_id,
                    index,
                    chunk_for_storage,
                    sanitized_value,
                    scope,
                    owner_user_id,
                    org_id,
                    metadata["tech_tags"],
                    metadata["error_type"],
                ),
            )
            row = cur.fetchone()
            cur.execute(
                """
                insert into public.embeddings (chunk_id, embedding, scope, owner_user_id, org_id)
                values (%s, %s, %s, %s, %s)
                """,
                (row["id"], Vector(embedding), scope, owner_user_id, org_id),
            )

    def ingest_file(
        self,
        *,
        user_id: str,
        filename: str,
        data: bytes,
        scope: str,
        org_id: Optional[str],
        contribute_global: bool,
        mime_type: Optional[str],
    ) -> IngestionResult:
        if scope not in {"user", "org"}:
            raise ValueError("scope must be 'user' or 'org' for user uploads")
        if scope == "org" and not org_id:
            raise ValueError("org_id is required when scope is 'org'")

        entries = self._extract_text_entries(filename, data)
        if not entries:
            raise ValueError("No text content extracted from uploaded file")

        storage_path = self._persist_upload_file(user_id=user_id, filename=filename, data=data)
        combined_title = filename if len(entries) == 1 else f"{filename} ({len(entries)} entries)"

        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                if scope == "org" and org_id and not self._is_org_member(cur, user_id=user_id, org_id=org_id):
                    raise ValueError("User is not a member of the specified organization")

                owner = user_id
                document_id = self._insert_document(
                    cur,
                    title=combined_title,
                    mime_type=mime_type,
                    source_type="upload",
                    scope=scope,
                    owner_user_id=owner,
                    org_id=org_id if scope == "org" else None,
                    storage_path=storage_path,
                    contributed_to_global=False,
                )

                all_chunks: List[str] = []
                for entry in entries:
                    all_chunks.extend(self.splitter.split_text(entry["text"]))
                all_chunks = [chunk.strip() for chunk in all_chunks if chunk and chunk.strip()]
                if not all_chunks:
                    raise ValueError("Extracted content is empty after chunking")

                self._insert_chunks_and_embeddings(
                    cur,
                    document_id=document_id,
                    chunks=all_chunks,
                    scope=scope,
                    owner_user_id=owner,
                    org_id=org_id if scope == "org" else None,
                )

                global_document_id: Optional[str] = None
                if contribute_global:
                    global_document_id = self._insert_document(
                        cur,
                        title=f"[global-anonymized] {combined_title}",
                        mime_type="text/plain",
                        source_type="opt_in_anonymized",
                        scope="global",
                        owner_user_id=None,
                        org_id=None,
                        storage_path=None,
                        contributed_to_global=True,
                    )
                    self._insert_chunks_and_embeddings(
                        cur,
                        document_id=global_document_id,
                        chunks=all_chunks,
                        scope="global",
                        owner_user_id=None,
                        org_id=None,
                        force_sanitized=True,
                    )

            conn.commit()

        return IngestionResult(
            document_id=document_id,
            chunk_count=len(all_chunks),
            global_document_id=global_document_id,
            storage_path=storage_path,
        )

    def _search_scope(
        self,
        cur: psycopg.Cursor,
        *,
        scope: str,
        query_embedding: Vector,
        user_id: str,
        org_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []

        if scope == "org":
            if not org_id:
                return []
            cur.execute(
                """
                select
                    c.id as chunk_id,
                    c.document_id,
                    c.scope,
                    c.owner_user_id,
                    c.org_id,
                    d.title as source_title,
                    c.content,
                    (1 - (e.embedding <=> %s))::float4 as similarity
                from public.embeddings e
                join public.chunks c on c.id = e.chunk_id
                join public.documents d on d.id = c.document_id
                where c.scope = 'org'
                  and c.org_id = %s
                  and exists (
                    select 1 from public.memberships m
                    where m.org_id = c.org_id and m.user_id = %s
                  )
                order by (e.embedding <=> %s)
                limit %s
                """,
                (query_embedding, org_id, user_id, query_embedding, limit),
            )
            return cur.fetchall()

        if scope == "user":
            cur.execute(
                """
                select
                    c.id as chunk_id,
                    c.document_id,
                    c.scope,
                    c.owner_user_id,
                    c.org_id,
                    d.title as source_title,
                    c.content,
                    (1 - (e.embedding <=> %s))::float4 as similarity
                from public.embeddings e
                join public.chunks c on c.id = e.chunk_id
                join public.documents d on d.id = c.document_id
                where c.scope = 'user'
                  and c.owner_user_id = %s
                order by (e.embedding <=> %s)
                limit %s
                """,
                (query_embedding, user_id, query_embedding, limit),
            )
            return cur.fetchall()

        cur.execute(
            """
            select
                c.id as chunk_id,
                c.document_id,
                c.scope,
                c.owner_user_id,
                c.org_id,
                d.title as source_title,
                coalesce(c.sanitized_content, c.content) as content,
                (1 - (e.embedding <=> %s))::float4 as similarity
            from public.embeddings e
            join public.chunks c on c.id = e.chunk_id
            join public.documents d on d.id = c.document_id
            where c.scope = 'global'
            order by (e.embedding <=> %s)
            limit %s
            """,
            (query_embedding, query_embedding, limit),
        )
        return cur.fetchall()

    def retrieve_context(
        self,
        *,
        user_id: str,
        query: str,
        org_id: Optional[str],
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        max_results = max(1, top_k)
        query_embedding = Vector(self.embeddings.embed_query(query))
        scoped_raw: Dict[str, List[Dict[str, Any]]] = {"org": [], "user": [], "global": []}

        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                for scope in SCOPE_PRIORITY:
                    if scope == "org" and not org_id:
                        continue
                    scoped_raw[scope] = self._search_scope(
                        cur,
                        scope=scope,
                        query_embedding=query_embedding,
                        user_id=user_id,
                        org_id=org_id,
                        limit=max_results,
                    )

        ordered_rows = prioritize_scoped_results(scoped_raw, max_results=max_results)
        normalized: List[Dict[str, Any]] = []
        for row in ordered_rows:
            normalized.append(
                {
                    "chunk_id": str(row["chunk_id"]),
                    "document_id": str(row["document_id"]),
                    "scope": row["scope"],
                    "owner_user_id": str(row["owner_user_id"]) if row["owner_user_id"] else None,
                    "org_id": str(row["org_id"]) if row["org_id"] else None,
                    "source_title": row["source_title"],
                    "content": row["content"],
                    "similarity": float(row["similarity"]),
                }
            )
        return normalized

    def save_analysis(
        self,
        *,
        user_id: str,
        org_id: Optional[str],
        input_error: str,
        output: Dict[str, Any],
        confidence: float,
        source_scopes: List[str],
    ) -> int:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.analyses (user_id, org_id, input_error, output, confidence, source_scopes)
                    values (%s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                    (user_id, org_id, input_error, json.dumps(output), confidence, source_scopes),
                )
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])
