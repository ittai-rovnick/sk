# Database-level permissions that cascade to all layers

## Context

Grant permissions (to users or groups) at the **database** level, so the principal automatically has access to **every layer in that database — existing and future** — without re-granting per layer.

### Current state

The **backend already supports live cascade**. The `permissions` table has `database_id` / `group_layer_id` / `layer_id` (exactly one must be set), and the `can_user_do()` Postgres function at [api/alembic/versions/001_initial_schema.py:256-315](../api/alembic/versions/001_initial_schema.py#L256-L315) resolves a layer's `database_id` and matches permission rows where `p.database_id = v_layer.database_id`. So any permission granted on a database applies at query-time to all layers in it — new layers included, zero extra rows.

What is **missing / broken**:

1. **UI** — [web/src/pages/PermissionsPage.tsx](../web/src/pages/PermissionsPage.tsx) has a Database/Layer toggle but no dedicated per-database view. No `DatabaseDetailPage`.
2. **Delegated admin** — [api/app/routers/permissions.py:74-75](../api/app/routers/permissions.py#L74-L75) hardcodes "superadmin required" for any database/group-layer grant. A database-admin role (can grant on one database) is not implementable today.
3. **User-grant bug** — [web/src/pages/PermissionsPage.tsx:81](../web/src/pages/PermissionsPage.tsx#L81) stores the user's **email** into `permissions.ms_user_id`, but `can_user_do()` checks against `ms_object_id` (Entra OID). Any user-level grant silently fails.
4. **Group-hierarchy inheritance** — [api/app/auth/microsoft.py:66-95](../api/app/auth/microsoft.py#L66-L95) only fetches direct custom-group memberships and MS-linked groups. It does **not** walk `parent_group_id` upward, so a permission granted on an ancestor group is not inherited by members of descendant groups. The hierarchy schema exists (migration 005) but isn't wired into auth.

## Decisions

- **Cascade model:** live cascade (no copying to per-layer rows).
- **UI location:** Permissions tab on each database.
- **Roles ladder:**
  - **Superadmin** — bypasses everything (unchanged: `users.is_superadmin`).
  - **Database admin** — user/group with a permission row at the *database* level whose role has `can_manage_perms=true` (= existing `admin` system role). Can grant/revoke any permission scoped to that database or any layer/group-layer in it.
  - **Editor / Viewer** — existing system roles, unchanged.

## Plan

### Backend

**1. New migration `006_perm_helpers.py`** — add a SQL function `can_manage_db_perms(p_ms_object_id, p_ms_group_ids, p_database_id) RETURNS BOOLEAN`. Mirrors the allow/deny logic of [can_user_do()](../api/alembic/versions/001_initial_schema.py#L256-L315) but scoped to a database and the `manage_perms` capability only.

**2. Fix group-hierarchy resolution** — in [api/app/auth/microsoft.py](../api/app/auth/microsoft.py) `resolve_custom_group_ids()`, after collecting direct + linked custom groups, walk `MsGroup.parent_group_id` upward (cap at `MAX_HIERARCHY_DEPTH=16`, matching the [groups router](../api/app/routers/groups.py)) and add every ancestor's `ms_group_id` to the returned list. One recursive CTE — no per-group round trips.

**3. New helper `can_user_manage_database_perms()`** in [api/app/auth/permissions.py](../api/app/auth/permissions.py) — thin wrapper around the new SQL function, same pattern as [can_user_do()](../api/app/auth/permissions.py#L6-L31). Returns `True` for superadmins.

**4. Rewrite authorization in [api/app/routers/permissions.py](../api/app/routers/permissions.py)**:

`POST /permissions` (grant):
- Superadmin → allow.
- Target is **layer**: allow if `can_user_do(layer_id, "manage_perms")` **OR** `can_user_manage_database_perms(layer.database_id)`.
- Target is **database**: allow if `can_user_manage_database_perms(database_id)`.
- Target is **group-layer**: look up `group_layer.database_id`, then `can_user_manage_database_perms(...)`.

`DELETE /permissions/{id}` (revoke): same three-way check on the existing row's scope.

**5. Principal directory** — the Permissions tab needs user/group lookup without requiring superadmin. Add `GET /users/directory` in [api/app/routers/users.py](../api/app/routers/users.py) returning `{id, email, display_name, ms_object_id}` to any authenticated user. Update `UserResponse` schema to include `ms_object_id`.

### Frontend

**6. Update types** — add `ms_object_id` to the `User` type in [web/src/types.ts](../web/src/types.ts).

**7. New page `web/src/pages/DatabaseDetailPage.tsx`** — tabs: **Info / Layers / Permissions**.
- **Info**: name, description, tags (reuse existing form).
- **Layers**: embed layer listing from [LayersPage.tsx](../web/src/pages/LayersPage.tsx) filtered to `database_id`.
- **Permissions**: reuse [PermissionMatrix](../web/src/components/permissions/PermissionMatrix.tsx); call `GET /permissions?database_id=:id` and `POST /permissions` with `database_id`. Banner: *"These permissions apply to every layer in this database, including layers created later."* Gate grant/revoke controls via a new `GET /databases/:id/my-capabilities` endpoint (so group-based admin rights resolve server-side).

**8. Routes** — in [web/src/App.tsx](../web/src/App.tsx) add `/databases/:id` → `DatabaseDetailPage`. Deep-link the Permissions tab via `?tab=permissions`.

**9. List-page entry point** — in [web/src/pages/DatabasesPage.tsx](../web/src/pages/DatabasesPage.tsx), make the row name clickable to the detail page and add a "Permissions" action that deep-links to `?tab=permissions`.

**10. Fix the `ms_user_id` bug** in [web/src/pages/PermissionsPage.tsx:81](../web/src/pages/PermissionsPage.tsx#L81): send `ms_object_id`, not `email`. Apply the same fix in the new DatabaseDetailPage grant flow. Without this, no user-level grant works at all.

## Critical files

**Modify:**
- [api/app/auth/microsoft.py](../api/app/auth/microsoft.py) — recursive group resolution
- [api/app/auth/permissions.py](../api/app/auth/permissions.py) — new wrapper
- [api/app/routers/permissions.py](../api/app/routers/permissions.py) — new authz rules
- [api/app/routers/users.py](../api/app/routers/users.py) — directory endpoint
- [api/app/schemas/users.py](../api/app/schemas/users.py) — expose `ms_object_id`
- [web/src/App.tsx](../web/src/App.tsx) — new route
- [web/src/pages/DatabasesPage.tsx](../web/src/pages/DatabasesPage.tsx) — navigation
- [web/src/pages/PermissionsPage.tsx](../web/src/pages/PermissionsPage.tsx) — bug fix
- [web/src/types.ts](../web/src/types.ts)

**Create:**
- `api/alembic/versions/006_perm_helpers.py`
- `web/src/pages/DatabaseDetailPage.tsx`

**Reuse:**
- [PermissionMatrix](../web/src/components/permissions/PermissionMatrix.tsx)
- [can_user_do()](../api/alembic/versions/001_initial_schema.py#L256-L315) PG function
- `admin` / `editor` / `viewer` system roles — already match the ladder

## Verification

```
docker compose up -d
cd api && venv\Scripts\alembic -x db=meta upgrade meta@head
cd api && venv\Scripts\python run.py
cd web && npm run dev
```

Scenarios (all must pass):

1. **Cascade to existing layers.** Superadmin grants group `G` viewer on DB `D`. A user in `G` reads every layer in `D`; a user not in `G` gets 403.
2. **Cascade to future layers.** After (1), create a new layer in `D`. Same `G` user has read access with no extra grant.
3. **Delegated admin.** Grant user `U` admin on `D`. Log in as `U` (not superadmin). On the DB Permissions tab, grant/revoke succeeds. Trying to manage a different database returns 403.
4. **User grant works.** Grant user `V` editor on `D` via the new UI. `V` has write access on layers in `D`. (Regression test for the `ms_user_id` bug.)
5. **Group hierarchy.** Parent `P`, child `C` (`C.parent_group_id = P.id`). User `W` in `C` only. Grant `P` viewer on `D`. `W` has read access.
6. **Deny wins.** Grant `G` viewer on `D`, then grant `U∈G` a deny on `D`. `U` is blocked.

Smoke: `/health` ok, Swagger shows `/users/directory`, web build clean.
