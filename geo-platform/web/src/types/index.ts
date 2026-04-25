export const GEOMETRY_TYPES = [
  "POINT", "LINESTRING", "POLYGON",
  "MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON",
] as const;

export interface User {
  id: string;
  ms_object_id: string;
  email: string;
  display_name: string | null;
  is_superadmin: boolean;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string;
}

export interface GeoDatabase {
  id: string;
  name: string;
  description: string | null;
  default_srid: number;
  tags: string[];
  created_at: string;
}

export interface GroupLayer {
  id: string;
  database_id: string;
  parent_id: string | null;
  name: string;
  description: string | null;
  tags: string[];
  sort_order: number;
  created_at: string;
  children?: GroupLayer[];
  layers?: Layer[];
}

export interface Layer {
  id: string;
  database_id: string;
  group_layer_id: string | null;
  name: string;
  description: string | null;
  geometry_types: string[];
  srid: number;
  tags: string[];
  status: "draft" | "review" | "published";
  health: "ok" | "stale" | "error" | "syncing";
  shard_id: number;
  is_locked: boolean;
  lock_reason: string | null;
  locked_at: string | null;
  sort_order: number;
  bbox: [number, number, number, number] | null;
  features_updated_at: string | null;
  features_updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LayerStyle {
  id: string;
  layer_id: string;
  name: string;
  renderer: Record<string, unknown>;
  label_config: Record<string, unknown> | null;
  popup_config: Record<string, unknown> | null;
  is_default: boolean;
  lyrx_s3_key: string | null;
  created_at: string;
}

export interface Permission {
  id: string;
  ms_user_id: string | null;
  ms_group_id: string | null;
  database_id: string | null;
  group_layer_id: string | null;
  layer_id: string | null;
  role_id: string;
  allow: boolean;
  granted_at: string;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  can_read: boolean;
  can_write: boolean;
  can_delete: boolean;
  can_export: boolean;
  can_manage_style: boolean;
  can_manage_perms: boolean;
  can_publish: boolean;
}

export interface AuditEntry {
  id: number;
  user_id: string | null;
  ms_object_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  old_value: unknown;
  new_value: unknown;
  ip_address: string | null;
  created_at: string;
}

export interface SyncConflict {
  id: string;
  layer_id: string;
  feature_id: number;
  user_id: string;
  device_id: string;
  client_payload: Record<string, unknown>;
  server_version: number;
  client_version: number;
  resolution: "server_wins" | "client_wins" | "manual" | "pending";
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

// ── Maps ───────────────────────────────────────────────────────────────────────

export interface GeoMap {
  id: string;
  database_id: string;
  name: string;
  description: string | null;
  extent: [number, number, number, number] | null;
  content_version: number;
  content_updated_at: string;
  content_updated_by: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface MapGroup {
  id: string;
  map_id: string;
  parent_id: string | null;
  embedded_map_id: string | null;
  name: string;
  sort_order: number;
  is_expanded: boolean;
  created_at: string;
}

export interface MapLayerNode {
  type: "layer";
  map_layer_id: string;
  layer_id: string;
  name: string;
  group_id: string | null;
  sort_order: number;
  is_visible: boolean;
  srid: number;
  geometry_types: string[];
  bbox: [number, number, number, number] | null;
  filter_expression: object | null;
  effective_role?: string;
}

export interface MapGroupNode {
  type: "group";
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  is_expanded: boolean;
  embedded_map_id: string | null;
  children: (MapGroupNode | MapLayerNode)[];
}

export type MapTreeNode = MapGroupNode | MapLayerNode;

export interface MapOpenResponse {
  map: GeoMap;
  tree: MapTreeNode[];
}

export interface MapFreshnessChangedLayer {
  layer_id: string;
  name: string;
  features_updated_at: string | null;
  features_updated_by: string | null;
}

export interface MapFreshnessResponse {
  map_id: string;
  content_version: number;
  content_updated_at: string;
  any_change_since: boolean;
  changed_layers: MapFreshnessChangedLayer[];
}

// ── Stats ──────────────────────────────────────────────────────────────────────

export type FieldStat =
  | { type: "string";  null_count: number; unique_count: number; top_values: { value: string; count: number }[] }
  | { type: "number";  min: number | null; max: number | null; avg: number | null; null_count: number }
  | { type: "boolean"; true_count: number; false_count: number; null_count: number }
  | { type: string;    error?: string };

export interface LayerStats {
  layer_id: string;
  total_count: number;
  geometry_type_counts: Record<string, number>;
  bbox: [number, number, number, number] | null;
  field_stats: Record<string, FieldStat>;
}

// ── Identify ───────────────────────────────────────────────────────────────────

export interface IdentifyLayerNode {
  type: "layer";
  layer_id: string;
  name: string;
  feature_count_in_area: number;
  geometry_types: string[];
  bbox: [number, number, number, number] | null;
}

export interface IdentifyGroupNode {
  type: "group";
  id: string;
  name: string;
  features_in_area: number;
  children: IdentifyLayerNode[];
}

export type IdentifyTreeNode = IdentifyGroupNode | IdentifyLayerNode;

export interface LayerIdentifyResponse {
  tree: IdentifyTreeNode[];
}

// ── Versions / Expressions (for layer detail page) ─────────────────────────────

export interface VersionListItem {
  id: number;
  version: number;
  changed_fields: string[];
  changed_by: string | null;
  changed_at: string;
  message: string | null;
}

export interface VersionDetail extends VersionListItem {
  snapshot: Record<string, unknown>;
}

export interface SavedExpressionListItem {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface SavedExpressionDetail extends SavedExpressionListItem {
  layer_id: string;
  expression: Record<string, unknown>;
  created_by: string | null;
  updated_at: string;
}
