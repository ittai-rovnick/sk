import { useState, useEffect } from "react";
import { Table, Tag, Typography, Space, Button, Modal, Form, Input, Switch, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import client from "../api/client";
import type { User } from "../types";

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  function load() {
    setLoading(true);
    client.get<User[]>("/users").then((r) => setUsers(r.data)).finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function onCreate(values: { email: string; display_name?: string; is_superadmin?: boolean }) {
    setSaving(true);
    try {
      await client.post("/users", values);
      message.success("User created");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch {
      message.error("Failed to create user");
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    { title: "Name", dataIndex: "display_name", key: "display_name" },
    { title: "Email", dataIndex: "email", key: "email" },
    {
      title: "Role",
      dataIndex: "is_superadmin",
      key: "role",
      render: (v: boolean) => <Tag color={v ? "red" : "blue"}>{v ? "Superadmin" : "User"}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "Active" : "Inactive"}</Tag>,
    },
    {
      title: "Last seen",
      dataIndex: "last_seen_at",
      key: "last_seen",
      render: (v: string | null) => v ? new Date(v).toLocaleDateString() : "—",
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Users</Typography.Title>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setModalOpen(true)}>New user</Button>
      </Space>

      <Table rowKey="id" dataSource={users} columns={columns} loading={loading} />

      <Modal
        title="Create user"
        open={modalOpen}
        onOk={form.submit}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" onFinish={onCreate}>
          <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="display_name" label="Display name">
            <Input />
          </Form.Item>
          <Form.Item name="is_superadmin" label="Superadmin" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
