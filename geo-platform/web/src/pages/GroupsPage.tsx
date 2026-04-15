import { Table, Button, Typography, Space } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { groups as groupApi } from "../api/groups";

export function GroupsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["groups"], queryFn: groupApi.list });

  const sync = useMutation({
    mutationFn: groupApi.sync,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["groups"] }),
  });

  const columns = [
    { title: "Display name", dataIndex: "display_name", key: "display_name" },
    { title: "Group ID", dataIndex: "ms_group_id", key: "ms_group_id" },
    {
      title: "Last synced",
      dataIndex: "synced_at",
      render: (v: string | null) => v ? new Date(v).toLocaleDateString() : "Never",
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Groups</Typography.Title>
        <Button icon={<SyncOutlined />} onClick={() => sync.mutate()} loading={sync.isPending}>
          Sync from Microsoft
        </Button>
      </Space>
      <Table rowKey="id" dataSource={data} columns={columns} loading={isLoading} />
    </>
  );
}
