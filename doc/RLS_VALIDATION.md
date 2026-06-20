# RLS Validation Checklist (Negative Tests)

Use two real Supabase users:

- `user_a` (member of `org_alpha`)
- `user_b` (not member of `org_alpha`)

Run each test through a client that sends the user's access token (or in SQL editor by setting claim variables).

## 1) Org isolation

1. As `user_a`, insert an org-scoped doc/chunk for `org_alpha`.
2. As `user_b`, call `POST /v2/analyze` with `org_id=org_alpha`.
3. Expected:
   - No org sources from `org_alpha` appear in `sources`.
   - Query does not leak chunk text from `org_alpha`.

## 2) User-private isolation

1. As `user_a`, upload a user-scoped file (`scope=user`) with a unique string.
2. As `user_b`, search for that unique string with `POST /v2/analyze`.
3. Expected:
   - No `scope=user` source from `user_a` is returned.

## 3) Global visibility

1. As `user_a`, upload with `contribute_global=true`.
2. As `user_b`, run `POST /v2/analyze` with matching query.
3. Expected:
   - `scope=global` source can appear.
   - Content is sanitized (`[REDACTED_*]` markers), never raw secrets.

## 4) Membership checks for upload

1. As `user_b` (non-member), try `POST /v2/upload` with `scope=org` and `org_id=org_alpha`.
2. Expected:
   - Request fails with `400` and membership error.

## 5) Role checks for membership management

1. Ensure `user_b` is a regular member in an org.
2. Attempt to insert/update/delete another member directly (or via API endpoint if added).
3. Expected:
   - Denied unless role is `owner` or `admin`.
