import { useState, useEffect, useCallback, useRef } from "react";
import {
  Table, Button, Space, Tag, message, Popconfirm,
  Input, InputNumber, Switch, DatePicker,
} from "antd";
import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import client from "../../api/client";

interface FieldDef {
  name: string;
  type: "string" | "number" | "boolean" | "date";
  required: boolean;
}

interface LayerSchemaResponse {
  layer_id: string;
  json_schema: { fields?: FieldDef[] };
  schema_version: number;
}

interface ApiFeature {
  id: number;
  layer_id: string;
  geom: GeoJSON.Geometry;
  properties: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
}

interface Props {
  layerId: string;
  refreshKey?: number;
  onFeaturesChanged?: () => void;
}

function geomLabel(geom: GeoJSON.Geometry): string {
  return geom?.type ?? "—";
}

function formatCell(value: unknown, type: string): string {
  if (value == null) return "";
  if (type === "boolean") return value ? "Yes" : "No";
  if (type === "date") {
    const d = new Date(String(value));
    return isNaN(d.getTime()) ? String(value) : d.toLocaleDateString();
  }
  return String(value);
}

// ── Editable cell ────────────────────────────────────────────────────────────

interface EditableCellProps {
  value: unknown;
  field: FieldDef;
  onSave: (newValue: unknown) => Promise<void>;
}

function EditableCell({ value, field, onSave }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<unknown>(value);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus();
  }, [editing]);

  async function commit(newVal: unknown) {
    if (newVal === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(newVal);
      setEditing(false);
    } catch {
      message.error("Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function clear() {
    setSaving(true);
    try {
      await onSave(null);
      setDraft(null);
      setEditing(false);
    } catch {
      message.error("Clear failed");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    const display = formatCell(value, field.type);
    return (
      <div
        onClick={() => setEditing(true)}
        style={{
          minHeight: 22,
          cursor: "pointer",
          padding: "0 4px",
          borderRadius: 3,
          color: display ? undefined : "#bfbfbf",
        }}
        title="Click to edit"
      >
        {display || "—"}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <Space size={4}>
        <Switch
          size="small"
          checked={!!draft}
          loading={saving}
          onChange={(v) => commit(v)}
        />
        {value != null && (
          <Button size="small" type="link" danger onClick={clear} disabled={saving} style={{ padding: 0, fontSize: 11 }}>
            clear
          </Button>
        )}
        <Button size="small" type="link" onClick={() => setEditing(false)} style={{ padding: 0, fontSize: 11 }}>
          cancel
        </Button>
      </Space>
    );
  }

  if (field.type === "number") {
    return (
      <Space size={4}>
        <InputNumber
          ref={inputRef as never}
          size="small"
          value={draft as number}
          style={{ width: 100 }}
          disabled={saving}
          onChange={(v) => setDraft(v)}
          onPressEnter={() => commit(draft)}
          onBlur={() => commit(draft)}
        />
        {value != null && (
          <Button size="small" type="link" danger onClick={clear} disabled={saving} style={{ padding: 0, fontSize: 11 }}>
            clear
          </Button>
        )}
      </Space>
    );
  }

  if (field.type === "date") {
    const draftDay = draft ? dayjs(String(draft)) : null;
    return (
      <Space size={4}>
        <DatePicker
          size="small"
          value={draftDay?.isValid() ? draftDay : null}
          disabled={saving}
          onChange={(d) => commit(d ? d.toISOString() : null)}
          style={{ width: 130 }}
        />
        {value != null && (
          <Button size="small" type="link" danger onClick={clear} disabled={saving} style={{ padding: 0, fontSize: 11 }}>
            clear
          </Button>
        )}
      </Space>
    );
  }

  // string (default)
  return (
    <Space size={4}>
      <Input
        ref={inputRef as never}
        size="small"
        value={String(draft ?? "")}
        style={{ width: 160 }}
        disabled={saving}
        onChange={(e) => setDraft(e.target.value)}
        onPressEnter={() => commit(draft)}
        onBlur={() => commit(draft)}
      />
      {value != null && (
        <Button size="small" type="link" danger onClick={clear} disabled={saving} style={{ padding: 0, fontSize: 11 }}>
          clear
        </Button>
      )}
    </Space>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export function AttributeTable({ layerId, refreshKey, onFeaturesChanged }: Props) {
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [features, setFeatures] = useState<ApiFeature[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [schemaRes, featRes] = await Promise.all([
        client.get<LayerSchemaResponse>(`/layers/${layerId}/schema`),
        client.get<ApiFeature[]>(`/layers/${layerId}/features?limit=5000`),
      ]);
      setFields(schemaRes.data.json_schema?.fields ?? []);
      setFeatures(featRes.data);
      setSelectedIds([]);
    } catch {
      message.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [layerId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (refreshKey != null && refreshKey > 0) load();
  }, [refreshKey, load]);

  async function saveProperty(feature: ApiFeature, fieldName: string, newValue: unknown) {
    const updatedProps = { ...feature.properties };
    if (newValue == null) {
      delete updatedProps[fieldName];
    } else {
      updatedProps[fieldName] = newValue;
    }
    await client.put(`/layers/${layerId}/features/${feature.id}`, {
      properties: updatedProps,
      version: feature.version,
    });
    setFeatures((prev) =>
      prev.map((f) =>
        f.id === feature.id
          ? { ...f, properties: updatedProps, version: f.version + 1 }
          : f,
      ),
    );
    onFeaturesChanged?.();
  }

  async function bulkDelete() {
    if (selectedIds.length === 0) return;
    setDeleting(true);
    try {
      const res = await client.post<{ deleted: number }>(
        `/layers/${layerId}/features/bulk-delete`,
        { feature_ids: selectedIds },
      );
      message.success(`Deleted ${res.data.deleted} feature(s)`);
      setSelectedIds([]);
      await load();
      onFeaturesChanged?.();
    } catch {
      message.error("Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  const columns: ColumnsType<ApiFeature> = [
    {
      title: "ID",
      dataIndex: "id",
      key: "id",
      width: 70,
      sorter: (a, b) => a.id - b.id,
      defaultSortOrder: "ascend",
    },
    {
      title: "Geometry",
      key: "geom_type",
      width: 110,
      render: (_, row) => <Tag>{geomLabel(row.geom)}</Tag>,
    },
    ...fields.map((f) => ({
      title: f.name,
      key: `prop_${f.name}`,
      width: f.type === "boolean" ? 100 : f.type === "date" ? 160 : 170,
      render: (_: unknown, row: ApiFeature) => (
        <EditableCell
          value={row.properties[f.name]}
          field={f}
          onSave={(v) => saveProperty(row, f.name, v)}
        />
      ),
    })),
    {
      title: "Updated",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 110,
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* ── Toolbar ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "4px 12px", borderBottom: "1px solid #f0f0f0", flexShrink: 0,
      }}>
        <Tag>{features.length} rows</Tag>
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          Refresh
        </Button>
        {selectedIds.length > 0 && (
          <Popconfirm
            title={`Delete ${selectedIds.length} feature(s)?`}
            onConfirm={bulkDelete}
          >
            <Button size="small" danger icon={<DeleteOutlined />} loading={deleting}>
              Delete ({selectedIds.length})
            </Button>
          </Popconfirm>
        )}
      </div>

      {/* ── Table ── */}
      <div style={{ flex: 1, overflow: "hidden" }}>
        <Table
          rowKey="id"
          dataSource={features}
          columns={columns}
          loading={loading}
          size="small"
          pagination={{ pageSize: 50, showSizeChanger: true, pageSizeOptions: ["25", "50", "100", "500"], size: "small" }}
          scroll={{ x: "max-content", y: "100%" }}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys as number[]),
          }}
        />
      </div>
    </div>
  );
}
