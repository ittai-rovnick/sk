import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Select, Typography, Space, Button, Table, Tag, Modal, Form,
  Input, message, Tooltip, Badge,
} from "antd";
import {
  PlusOutlined, EyeOutlined, LockOutlined, UnlockOutlined, DeleteOutlined,
} from "@ant-design/icons";
import client from "../api/client";
import type { GeoDatabase, Layer } from "../types";

const STATUS_COLOR: Record<string, string> = { draft: "default", review: "orange", published: "green" };
const HEALTH_COLOR: Record<string, string> = { ok: "success", stale: "warning", error: "error", syncing: "processing" };

export function LayersPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const dbId = searchParams.get("database_id") ?? "";

  const [databases, setDatabases] = useState<GeoDatabase[]>([]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [loadingLayers, setLoadingLayers] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editLayer, setEditLayer] = useState<Layer | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    client.get<GeoDatabase[]>("/databases").then((r) => setDatabases(r.data));
  }, []);

  useEffect(() => {
    if (!dbId) return;
    setLoadingLayers(true);
    client.get<Layer[]>(`/layers?database_id=${dbId}`)
      .then((r) => setLayers(r.data))
      .finally(() => setLoadingLayers(false));
  }, [dbId]);

  async function onCreate(values: Record<string, unknown>) {
    setSaving(true);
    try {
      await client.post("/layers", { ...values, database_id: dbId, srid: 4326 });
      message.success("Layer created");
      setCreateOpen(false);
      form.resetFields();
      refreshLayers();
    } catch {
      message.error("Failed to create layer");
    } finally {
      setSaving(false);
    }
  }

  async function onEdit(values: Record<string, unknown>) {
    if (!editLayer) return;
    setSaving(true);
    try {
      await client.put(`/layers/${editLayer.id}`, values);
      message.success("Layer updated");
      setEditLayer(null);
      refreshLayers();
    } catch {
      message.error("Failed to update layer");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(layer: Layer) {
    try {
      await client.delete(`/layers/${layer.id}`);
      message.success("Layer deleted");
      refreshLayers();
    } catch {
      message.error("Failed to delete layer");
    }
  }

  async function onToggleLock(layer: Layer) {
    try {
      if (layer.is_locked) {
        await client.delete(`/layers/${layer.id}/lock`);
        message.success("Layer unlocked");
      } else {
        await client.post(`/layers/${layer.id}/lock`, { reason: "Locked via UI" });
        message.success("Layer locked");
      }
      refreshLayers();
    } catch {
      message.error("Failed to toggle lock");
    }
  }

  function refreshLayers() {
    if (!dbId) return;
    client.get<Layer[]>(`/layers?database_id=${dbId}`).then((r) => setLayers(r.data));
  }

  function openEdit(layer: Layer) {
    setEditLayer(layer);
    form.setFieldsValue({
      name: layer.name,
      description: layer.description,
      tags: layer.tags,
    });
  }

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, row: Layer) => (
        <Space>
          {row.is_locked && <LockOutlined style={{ color: "#faad14" }} />}
          <Typography.Text strong>{name}</Typography.Text>
        </Space>
      ),
    },
    {
      title: "Geometry",
      dataIndex: "geometry_types",
      key: "geometry_types",
      width: 200,
      render: (types: string[]) =>
        types?.length
          ? <Space size={4} wrap>{types.map((t) => <Tag key={t}>{t}</Tag>)}</Space>
          : <Tag color="default">empty</Tag>,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
    },
    {
      title: "Health",
      dataIndex: "health",
      key: "health",
      width: 100,
      render: (h: string) => <Badge status={HEALTH_COLOR[h] as never} text={h} />,
    },
    {
      title: "Updated",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 120,
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
    {
      title: "",
      key: "actions",
      width: 150,
      render: (_: unknown, row: Layer) => (
        <Space>
          <Tooltip title="View map">
            <Button icon={<EyeOutlined />} size="small" onClick={() => navigate(`/layers/${row.id}`)} />
          </Tooltip>
          <Tooltip title={row.is_locked ? "Unlock" : "Lock"}>
            <Button
              icon={row.is_locked ? <UnlockOutlined /> : <LockOutlined />}
              size="small"
              onClick={() => onToggleLock(row)}
            />
          </Tooltip>
          <Tooltip title="Edit">
            <Button size="small" onClick={() => openEdit(row)}>Edit</Button>
          </Tooltip>
          <Tooltip title="Delete">
            <Button
              icon={<DeleteOutlined />}
              size="small"
              danger
              onClick={() => Modal.confirm({
                title: `Delete "${row.name}"?`,
                onOk: () => onDelete(row),
              })}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const isEditing = !!editLayer;

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>Layers</Typography.Title>
        <Select
          placeholder="Select database"
          style={{ width: 240 }}
          value={dbId || undefined}
          options={databases.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(v) => setSearchParams({ database_id: v })}
        />
        {dbId && (
          <Button icon={<PlusOutlined />} type="primary" onClick={() => { form.resetFields(); setCreateOpen(true); }}>
            New layer
          </Button>
        )}
      </Space>

      {!dbId ? (
        <Typography.Text type="secondary">Select a database to see its layers.</Typography.Text>
      ) : (
        <Table rowKey="id" dataSource={layers} columns={columns} loading={loadingLayers} />
      )}

      {/* Create / Edit modal */}
      <Modal
        title={isEditing ? `Edit "${editLayer?.name}"` : "New layer"}
        open={createOpen || isEditing}
        onOk={form.submit}
        onCancel={() => { setCreateOpen(false); setEditLayer(null); form.resetFields(); }}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" onFinish={isEditing ? onEdit : onCreate}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Select mode="tags" placeholder="Press enter to add tags" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
