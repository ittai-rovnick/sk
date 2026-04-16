import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Modal, Form, Input, Tag, Select, Space, Typography, message } from "antd";
import { PlusOutlined, FolderOpenOutlined } from "@ant-design/icons";
import client from "../api/client";
import type { GeoDatabase } from "../types";

export function DatabasesPage() {
  const navigate = useNavigate();
  const [databases, setDatabases] = useState<GeoDatabase[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  async function load() {
    setLoading(true);
    try {
      const res = await client.get<GeoDatabase[]>("/databases");
      setDatabases(res.data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function onCreate(values: { name: string; description?: string; tags?: string[] }) {
    setSaving(true);
    try {
      await client.post("/databases", { default_srid: 4326, tags: [], ...values });
      message.success("Database created");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch {
      message.error("Failed to create database");
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    { title: "Description", dataIndex: "description", key: "description" },
    {
      title: "SRID",
      dataIndex: "default_srid",
      key: "srid",
      width: 80,
    },
    {
      title: "Tags",
      dataIndex: "tags",
      key: "tags",
      render: (tags: string[]) => tags.map((t) => <Tag key={t}>{t}</Tag>),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
    {
      title: "",
      key: "actions",
      width: 120,
      render: (_: unknown, row: GeoDatabase) => (
        <Button
          icon={<FolderOpenOutlined />}
          size="small"
          onClick={() => navigate(`/layers?database_id=${row.id}`)}
        >
          Layers
        </Button>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Databases
        </Typography.Title>
        <Button
          icon={<PlusOutlined />}
          type="primary"
          onClick={() => setModalOpen(true)}
        >
          New database
        </Button>
      </Space>

      <Table rowKey="id" dataSource={databases} columns={columns} loading={loading} />

      <Modal
        title="Create database"
        open={modalOpen}
        onOk={form.submit}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" onFinish={onCreate}>
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
