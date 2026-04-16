import { useState, useEffect } from "react";
import { Table, Tag, Button, Typography, Space, message, Divider } from "antd";
import client from "../api/client";
import type { SyncConflict } from "../types";
import { DrawMap } from "../components/shared/DrawMap";

const RESOLUTION_COLOR: Record<string, string> = {
  pending: "orange",
  server_wins: "green",
  client_wins: "blue",
  manual: "purple",
};

export function SyncConflictsPage() {
  const [conflicts, setConflicts] = useState<SyncConflict[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    client.get<SyncConflict[]>("/sync/conflicts").then((r) => setConflicts(r.data)).finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function resolve(id: string, resolution: string) {
    try {
      await client.patch(`/sync/conflicts/${id}`, { resolution });
      message.success("Resolved");
      load();
    } catch {
      message.error("Failed to resolve conflict");
    }
  }

  const columns = [
    { title: "Layer", dataIndex: "layer_id", key: "layer_id" },
    { title: "Feature", dataIndex: "feature_id", key: "feature_id" },
    { title: "Device", dataIndex: "device_id", key: "device_id" },
    {
      title: "Versions",
      key: "versions",
      render: (_: unknown, row: SyncConflict) =>
        `server: ${row.server_version} / client: ${row.client_version}`,
    },
    {
      title: "Resolution",
      dataIndex: "resolution",
      key: "resolution",
      render: (v: string) => <Tag color={RESOLUTION_COLOR[v]}>{v}</Tag>,
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, row: SyncConflict) =>
        row.resolution === "pending" && (
          <Space>
            <Button size="small" onClick={() => resolve(row.id, "server_wins")}>Server wins</Button>
            <Button size="small" onClick={() => resolve(row.id, "client_wins")}>Client wins</Button>
          </Space>
        ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Sync Conflicts</Typography.Title>
      </Space>
      <Table rowKey="id" dataSource={conflicts} columns={columns} loading={loading} />

      <Divider />

      <Typography.Title level={4}>Map</Typography.Title>
      <DrawMap />
    </>
  );
}
