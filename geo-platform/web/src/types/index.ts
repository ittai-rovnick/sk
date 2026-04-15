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
  geometry_type: string;
  srid: number;
  tags: string[];
  status: "draft" | "review" | "published";
  health: "ok" | "stale" | "error" | "syncing";
  shard_id: number;
  is_locked: boolean;
  lock_reason: string | null;
  locked_at: string | null;
  sort_order: number;
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
