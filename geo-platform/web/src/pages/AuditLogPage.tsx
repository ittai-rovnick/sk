import { useState, useEffect } from "react";
import { Table, Typography, Space } from "antd";
import client from "../api/client";
import type { AuditEntry } from "../types";

export function AuditLogPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client.get<AuditEntry[]>("/audit").then((r) => setEntries(r.data)).finally(() => setLoading(false));
  }, []);

  const columns = [
    { title: "Action", dataIndex: "action", key: "action" },
    { title: "Resource", dataIndex: "resource_type", key: "resource_type" },
    { title: "Resource ID", dataIndex: "resource_id", key: "resource_id" },
    {
      title: "When",
      dataIndex: "created_at",
      key: "created_at",
      render: (v: string) => new Date(v).toLocaleString(),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Audit Log</Typography.Title>
      </Space>
      <Table rowKey="id" dataSource={entries} columns={columns} loading={loading} />
    </>
  );
}
