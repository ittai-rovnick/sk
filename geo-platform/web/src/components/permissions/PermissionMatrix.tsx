import { Table, Tag, Space } from "antd";
import type { Permission, Role } from "../../types";

interface Props {
  permissions: Permission[];
  roles: Role[];
  onRevoke: (id: string) => void;
}

export function PermissionMatrix({ permissions, roles, onRevoke }: Props) {
  const roleMap = Object.fromEntries(roles.map((r) => [r.id, r]));

  const columns = [
    {
      title: "Principal",
      render: (_: unknown, row: Permission) =>
        row.ms_user_id ? `User: ${row.ms_user_id}` : `Group: ${row.ms_group_id}`,
    },
    {
      title: "Resource",
      render: (_: unknown, row: Permission) =>
        row.layer_id
          ? `Layer: ${row.layer_id}`
          : row.group_layer_id
          ? `Group: ${row.group_layer_id}`
          : `Database: ${row.database_id}`,
    },
    {
      title: "Role",
      render: (_: unknown, row: Permission) => roleMap[row.role_id]?.name ?? row.role_id,
    },
    {
      title: "Effect",
      render: (_: unknown, row: Permission) => (
        <Tag color={row.allow ? "green" : "red"}>{row.allow ? "Allow" : "Deny"}</Tag>
      ),
    },
    {
      title: "Actions",
      render: (_: unknown, row: Permission) => (
        <a onClick={() => onRevoke(row.id)} style={{ color: "red" }}>
          Revoke
        </a>
      ),
    },
  ];

  return <Table rowKey="id" dataSource={permissions} columns={columns} size="small" />;
}
