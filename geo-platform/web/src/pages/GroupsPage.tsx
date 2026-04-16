import { useState, useEffect } from "react";
import { Table, Button, Typography, Space, Tag, Modal, Form, Input, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import client from "../api/client";

interface Group {
  id: string;
  ms_group_id: string;
  display_name: string | null;
  description: string | null;
  is_custom: boolean;
  created_at: string;
}

export function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  function load() {
    setLoading(true);
    client.get<Group[]>("/groups").then((r) => setGroups(r.data)).finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function onCreate(values: { display_name: string; description?: string }) {
    setSaving(true);
    try {
      await client.post("/groups", values);
      message.success("Group created");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch {
      message.error("Failed to create group");
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    { title: "Name", dataIndex: "display_name", key: "display_name" },
    { title: "Description", dataIndex: "description", key: "description" },
    {
      title: "Type",
      dataIndex: "is_custom",
      key: "type",
      render: (v: boolean) => <Tag color={v ? "blue" : "purple"}>{v ? "Custom" : "MS Entra"}</Tag>,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Groups</Typography.Title>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setModalOpen(true)}>
          New group
        </Button>
      </Space>

      <Table rowKey="id" dataSource={groups} columns={columns} loading={loading} />

      <Modal
        title="Create group"
        open={modalOpen}
        onOk={form.submit}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" onFinish={onCreate}>
          <Form.Item name="display_name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
