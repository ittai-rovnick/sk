import { Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { users as userApi } from "../api/users";

export function UsersPage() {
  const { data, isLoading } = useQuery({ queryKey: ["users"], queryFn: userApi.list });

  const columns = [
    { title: "Name", dataIndex: "display_name", key: "display_name" },
    { title: "Email", dataIndex: "email", key: "email" },
    {
      title: "Status",
      dataIndex: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "red"}>{v ? "Active" : "Inactive"}</Tag>,
    },
    {
      title: "Superadmin",
      dataIndex: "is_superadmin",
      render: (v: boolean) => v ? <Tag color="purple">Yes</Tag> : null,
    },
    {
      title: "Last seen",
      dataIndex: "last_seen_at",
      render: (v: string | null) => v ? new Date(v).toLocaleDateString() : "Never",
    },
  ];

  return (
    <>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>Users</Typography.Title>
      <Table rowKey="id" dataSource={data} columns={columns} loading={isLoading} />
    </>
  );
}
