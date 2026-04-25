import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Table, Button, Modal, Form, Input, Select, Space, Typography, Popconfirm, message, Tag,
} from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, GlobalOutlined } from "@ant-design/icons";
import client from "../api/client";
import { mapsApi } from "../api/maps";
import type { GeoDatabase, GeoMap } from "../types";

export function MapsPage() {
  const navigate = useNavigate();
  const [databases, setDatabases] = useState<GeoDatabase[]>([]);
  const [selectedDb, setSelectedDb] = useState<string>("");
  const [maps, setMaps] = useState<GeoMap[]>([]);
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm<{ name: string; description?: string }>();
  const [creating, setCreating] = useState(false);

  const [editTarget, setEditTarget] = useState<GeoMap | null>(null);
  const [editForm] = Form.useForm<{ name: string; description?: string }>();
  const [editing, setEditing] = useState(false);

  // ── Load databases ──────────────────────────────────────────────────────────
  useEffect(() => {
    client.get<GeoDatabase[]>("/databases").then((r) => {
      setDatabases(r.data);
      if (r.data.length > 0 && !selectedDb) setSelectedDb(r.data[0].id);
    });
  }, []);

  // ── Load maps for selected DB ──────────────────────────────────────────────
  async function load() {
    if (!selectedDb) { setMaps([]); return; }
    setLoading(true);
    try {
      const rows = await mapsApi.list(selectedDb);
      setMaps(rows);
    } catch {
      message.error("Failed to load maps");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, [selectedDb]);

  // ── Create ──────────────────────────────────────────────────────────────────
  async function onCreate(values: { name: string; description?: string }) {
    if (!selectedDb) return;
    setCreating(true);
    try {
      await mapsApi.create({ ...values, database_id: selectedDb });
      message.success("Map created");
      setCreateOpen(false);
      createForm.resetFields();
      load();
    } catch {
      message.error("Failed to create map");
    } finally {
      setCreating(false);
    }
  }

  // ── Edit (rename / re-describe) ────────────────────────────────────────────
  function openEdit(m: GeoMap) {
    setEditTarget(m);
    editForm.setFieldsValue({ name: m.name, description: m.description ?? "" });
  }

  async function onEdit(values: { name: string; description?: string }) {
    if (!editTarget) return;
    setEditing(true);
    try {
      await mapsApi.update(editTarget.id, values);
      message.success("Map updated");
      setEditTarget(null);
      load();
    } catch {
      message.error("Failed to update map");
    } finally {
      setEditing(false);
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────
  async function onDelete(m: GeoMap) {
    try {
      await mapsApi.delete(m.id);
      message.success(`Deleted "${m.name}"`);
      load();
    } catch {
      message.error("Failed to delete");
    }
  }

  // ── Columns ────────────────────────────────────────────────────────────────
  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    { title: "Description", dataIndex: "description", key: "description" },
    {
      title: "Layers/Groups version",
      dataIndex: "content_version",
      key: "content_version",
      width: 160,
      render: (v: number) => <Tag>{`v${v}`}</Tag>,
    },
    {
      title: "Last content change",
      dataIndex: "content_updated_at",
      key: "content_updated_at",
      width: 200,
      render: (v: string) => v ? new Date(v).toLocaleString() : "—",
    },
    {
      title: "",
      key: "actions",
      width: 240,
      render: (_: unknown, row: GeoMap) => (
        <Space>
          <Button
            size="small"
            icon={<GlobalOutlined />}
            onClick={() => navigate(`/map?map_id=${row.id}`)}
          >
            Open
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            Rename
          </Button>
          <Popconfirm
            title={`Delete "${row.name}"?`}
            description="The map's groups and layer associations are removed; underlying layers stay."
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={() => onDelete(row)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>Maps</Typography.Title>
        <Select
          placeholder="Select database"
          value={selectedDb || undefined}
          options={databases.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(v) => setSelectedDb(v)}
          style={{ minWidth: 240 }}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
          disabled={!selectedDb}
        >
          New map
        </Button>
      </Space>

      <Table rowKey="id" dataSource={maps} columns={columns} loading={loading} pagination={{ pageSize: 25 }} />

      {/* ── Create modal ── */}
      <Modal
        title="Create map"
        open={createOpen}
        onOk={createForm.submit}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        confirmLoading={creating}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" onFinish={onCreate}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Edit modal ── */}
      <Modal
        title="Edit map"
        open={!!editTarget}
        onOk={editForm.submit}
        onCancel={() => setEditTarget(null)}
        confirmLoading={editing}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" onFinish={onEdit}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
