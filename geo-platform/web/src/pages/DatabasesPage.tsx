import { useState } from "react";
import { Table, Button, Modal, Form, Input, Tag, Space, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { databases as dbApi } from "../api/databases";
import type { GeoDatabase } from "../types";

export function DatabasesPage() {
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const { data, isLoading } = useQuery({
    queryKey: ["databases"],
    queryFn: dbApi.list,
  });

  const create = useMutation({
    mutationFn: dbApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["databases"] });
      setModalOpen(false);
      form.resetFields();
    },
  });

  const columns = [
    { title: "Name", dataIndex: "name", key: "name" },
    { title: "Description", dataIndex: "description", key: "description" },
    {
      title: "Tags",
      dataIndex: "tags",
      render: (tags: string[]) => tags.map((t) => <Tag key={t}>{t}</Tag>),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Databases
        </Typography.Title>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setModalOpen(true)}>
          New database
        </Button>
      </Space>

      <Table rowKey="id" dataSource={data} columns={columns} loading={isLoading} />

      <Modal
        title="Create database"
        open={modalOpen}
        onOk={form.submit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={create.mutate}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Select mode="tags" placeholder="Add tags" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

// Local import to avoid circular — antd Select needed inside Form
import { Select } from "antd";
