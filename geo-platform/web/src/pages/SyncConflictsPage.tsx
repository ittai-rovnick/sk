import { Table, Tag, Button, Typography, Space } from "antd";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "../api/client";
import type { SyncConflict } from "../types";

export function SyncConflictsPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["conflicts"],
    queryFn: () =>
      client.get<SyncConflict[]>("/sync/conflicts").then((r) => r.data),
  });

  const resolve = useMutation({
    mutationFn: ({
      id,
      resolution,
    }: {
      id: string;
      resolution: "server_wins" | "client_wins";
    }) =>
      client
        .post(`/sync/conflicts/${id}/resolve`, { resolution })
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conflicts"] }),
  });

  const columns = [
    { title: "Layer ID", dataIndex: "layer_id", ellipsis: true },
    { title: "Feature ID", dataIndex: "feature_id", width: 100 },
    { title: "Device", dataIndex: "device_id", width: 160 },
    {
      title: "Versions",
      render: (_: unknown, row: SyncConflict) =>
        `Server: ${row.server_version} / Client: ${row.client_version}`,
      width: 180,
    },
    {
      title: "Status",
      dataIndex: "resolution",
      render: (v: string) => (
        <Tag color={v === "pending" ? "orange" : "green"}>{v}</Tag>
      ),
      width: 110,
    },
    {
      title: "Actions",
      render: (_: unknown, row: SyncConflict) =>
        row.resolution === "pending" ? (
          <Space>
            <Button
              size="small"
              onClick={() => resolve.mutate({ id: row.id, resolution: "server_wins" })}
            >
              Server wins
            </Button>
            <Button
              size="small"
              onClick={() => resolve.mutate({ id: row.id, resolution: "client_wins" })}
            >
              Client wins
            </Button>
          </Space>
        ) : null,
    },
  ];

  return (
    <>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>
        Sync Conflicts
      </Typography.Title>
      <Table
        rowKey="id"
        dataSource={data}
        columns={columns}
        loading={isLoading}
        size="small"
      />
    </>
  );
}
