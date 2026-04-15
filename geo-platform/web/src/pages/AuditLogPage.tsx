import { Table, Input, Select, DatePicker, Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import client from "../api/client";
import type { AuditEntry } from "../types";

const { RangePicker } = DatePicker;

export function AuditLogPage() {
  const [filters, setFilters] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => client.get<AuditEntry[]>("/audit", { params: filters }).then((r) => r.data),
  });

  const columns = [
    {
      title: "Time",
      dataIndex: "created_at",
      render: (v: string) => new Date(v).toLocaleString(),
      width: 180,
    },
    { title: "User", dataIndex: "ms_object_id", width: 200 },
    { title: "Action", dataIndex: "action", width: 120 },
    { title: "Resource type", dataIndex: "resource_type", width: 140 },
    { title: "Resource ID", dataIndex: "resource_id" },
    { title: "IP", dataIndex: "ip_address", width: 130 },
  ];

  return (
    <>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>Audit Log</Typography.Title>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="Filter by user ID"
          style={{ width: 240 }}
          onSearch={(v) => setFilters((f) => ({ ...f, ms_object_id: v }))}
          allowClear
        />
        <Select
          placeholder="Resource type"
          style={{ width: 160 }}
          allowClear
          options={["layer", "feature", "permission", "database"].map((v) => ({ value: v, label: v }))}
          onChange={(v) => setFilters((f) => ({ ...f, resource_type: v ?? "" }))}
        />
        <Select
          placeholder="Action"
          style={{ width: 140 }}
          allowClear
          options={["create", "update", "delete", "lock", "unlock"].map((v) => ({ value: v, label: v }))}
          onChange={(v) => setFilters((f) => ({ ...f, action: v ?? "" }))}
        />
      </Space>

      <Table
        rowKey="id"
        dataSource={data}
        columns={columns}
        loading={isLoading}
        size="small"
        pagination={{ pageSize: 50 }}
      />
    </>
  );
}
