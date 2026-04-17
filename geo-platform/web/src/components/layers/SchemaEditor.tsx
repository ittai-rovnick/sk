import { useState, useEffect } from "react";
import {
  Modal, Button, Input, Select, Switch, Table, message, Popconfirm,
} from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
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

const FIELD_TYPES = [
  { value: "string", label: "Text" },
  { value: "number", label: "Number" },
  { value: "boolean", label: "Yes / No" },
  { value: "date", label: "Date" },
];

interface Props {
  layerId: string;
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export function SchemaEditor({ layerId, open, onClose, onSaved }: Props) {
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    client
      .get<LayerSchemaResponse>(`/layers/${layerId}/schema`)
      .then((r) => setFields(r.data.json_schema?.fields ?? []))
      .catch(() => message.error("Failed to load schema"))
      .finally(() => setLoading(false));
  }, [layerId, open]);

  function addField() {
    setFields((prev) => [...prev, { name: "", type: "string", required: false }]);
  }

  function removeField(idx: number) {
    setFields((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateField(idx: number, patch: Partial<FieldDef>) {
    setFields((prev) =>
      prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)),
    );
  }

  async function save() {
    const names = fields.map((f) => f.name.trim()).filter(Boolean);
    if (new Set(names).size !== names.length) {
      message.warning("Field names must be unique");
      return;
    }
    if (fields.some((f) => !f.name.trim())) {
      message.warning("All fields must have a name");
      return;
    }
    setSaving(true);
    try {
      await client.put(`/layers/${layerId}/schema`, {
        json_schema: { fields: fields.map((f) => ({ ...f, name: f.name.trim() })) },
      });
      message.success("Schema saved");
      onSaved?.();
      onClose();
    } catch {
      message.error("Failed to save schema");
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    {
      title: "Field name",
      dataIndex: "name",
      key: "name",
      render: (_: string, __: FieldDef, idx: number) => (
        <Input
          size="small"
          placeholder="field_name"
          value={fields[idx].name}
          onChange={(e) => updateField(idx, { name: e.target.value })}
        />
      ),
    },
    {
      title: "Type",
      dataIndex: "type",
      key: "type",
      width: 120,
      render: (_: string, __: FieldDef, idx: number) => (
        <Select
          size="small"
          style={{ width: "100%" }}
          value={fields[idx].type}
          options={FIELD_TYPES}
          onChange={(v) => updateField(idx, { type: v as FieldDef["type"] })}
        />
      ),
    },
    {
      title: "Required",
      dataIndex: "required",
      key: "required",
      width: 80,
      render: (_: boolean, __: FieldDef, idx: number) => (
        <Switch
          size="small"
          checked={fields[idx].required}
          onChange={(v) => updateField(idx, { required: v })}
        />
      ),
    },
    {
      title: "",
      key: "actions",
      width: 40,
      render: (_: unknown, __: FieldDef, idx: number) => (
        <Popconfirm title="Remove field?" onConfirm={() => removeField(idx)}>
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Modal
      title="Layer fields"
      open={open}
      onCancel={onClose}
      onOk={save}
      confirmLoading={saving}
      width={520}
    >
      <Table
        rowKey={(_, idx) => String(idx)}
        dataSource={fields}
        columns={columns}
        pagination={false}
        loading={loading}
        size="small"
        locale={{ emptyText: "No fields defined yet" }}
        style={{ marginBottom: 12 }}
      />
      <Button icon={<PlusOutlined />} size="small" onClick={addField}>
        Add field
      </Button>
    </Modal>
  );
}
