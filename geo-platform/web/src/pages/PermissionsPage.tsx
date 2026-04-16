import { useState, useEffect } from "react";
import {
  Select, Typography, Space, Table, Tag, Button, Modal, Form,
  Radio, message, Tooltip,
} from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import client from "../api/client";
import type { GeoDatabase, Layer, Permission, Role } from "../types";

interface Group {
  id: string;
  ms_group_id: string;
  display_name: string | null;
}

interface User {
  id: string;
  email: string;
  display_name: string | null;
}

type ResourceType = "database" | "layer";

export function PermissionsPage() {
  const [resourceType, setResourceType] = useState<ResourceType>("layer");
  const [databases, setDatabases] = useState<GeoDatabase[]>([]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [selectedDbId, setSelectedDbId] = useState<string>("");
  const [selectedLayerId, setSelectedLayerId] = useState<string>("");
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loadingPerms, setLoadingPerms] = useState(false);
  const [grantOpen, setGrantOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    client.get<GeoDatabase[]>("/databases").then((r) => setDatabases(r.data));
    client.get<Role[]>("/permissions/roles").then((r) => setRoles(r.data));
    client.get<Group[]>("/groups").then((r) => setGroups(r.data));
    client.get<User[]>("/users").then((r) => setUsers(r.data));
  }, []);

  useEffect(() => {
    if (!selectedDbId) return;
    client.get<Layer[]>(`/layers?database_id=${selectedDbId}`).then((r) => setLayers(r.data));
  }, [selectedDbId]);

  const resourceId = resourceType === "database" ? selectedDbId : selectedLayerId;

  useEffect(() => {
    if (!resourceId) return;
    setLoadingPerms(true);
    const params = resourceType === "database" ? { database_id: resourceId } : { layer_id: resourceId };
    client.get<Permission[]>("/permissions", { params })
      .then((r) => setPermissions(r.data))
      .finally(() => setLoadingPerms(false));
  }, [resourceId, resourceType]);

  function refreshPerms() {
    if (!resourceId) return;
    const params = resourceType === "database" ? { database_id: resourceId } : { layer_id: resourceId };
    client.get<Permission[]>("/permissions", { params }).then((r) => setPermissions(r.data));
  }

  async function onGrant(values: {
    principal_type: "user" | "group";
    principal_id: string;
    role_id: string;
    allow: boolean;
  }) {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        role_id: values.role_id,
        allow: values.allow ?? true,
      };
      if (values.principal_type === "user") {
        body.ms_user_id = users.find((u) => u.id === values.principal_id)?.email;
      } else {
        body.ms_group_id = groups.find((g) => g.id === values.principal_id)?.ms_group_id;
      }
      if (resourceType === "database") body.database_id = resourceId;
      else body.layer_id = resourceId;

      await client.post("/permissions", body);
      message.success("Permission granted");
      setGrantOpen(false);
      form.resetFields();
      refreshPerms();
    } catch {
      message.error("Failed to grant permission");
    } finally {
      setSaving(false);
    }
  }

  async function onRevoke(perm: Permission) {
    try {
      await client.delete(`/permissions/${perm.id}`);
      message.success("Permission revoked");
      refreshPerms();
    } catch {
      message.error("Failed to revoke permission");
    }
  }

  function principalLabel(perm: Permission) {
    if (perm.ms_user_id) {
      const u = users.find((u) => u.email === perm.ms_user_id);
      return <Tag color="blue">{u?.display_name ?? perm.ms_user_id}</Tag>;
    }
    if (perm.ms_group_id) {
      const g = groups.find((g) => g.ms_group_id === perm.ms_group_id);
      return <Tag color="purple">{g?.display_name ?? perm.ms_group_id}</Tag>;
    }
    return "-";
  }

  function roleLabel(roleId: string) {
    return roles.find((r) => r.id === roleId)?.name ?? roleId;
  }

  const columns = [
    {
      title: "Principal",
      key: "principal",
      render: (_: unknown, row: Permission) => principalLabel(row),
    },
    { title: "Role", dataIndex: "role_id", key: "role", render: roleLabel },
    {
      title: "Effect",
      dataIndex: "allow",
      key: "allow",
      render: (allow: boolean) => <Tag color={allow ? "green" : "red"}>{allow ? "Allow" : "Deny"}</Tag>,
    },
    {
      title: "Granted",
      dataIndex: "granted_at",
      key: "granted_at",
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
    {
      title: "",
      key: "actions",
      width: 80,
      render: (_: unknown, row: Permission) => (
        <Tooltip title="Revoke">
          <Button
            icon={<DeleteOutlined />}
            size="small"
            danger
            onClick={() =>
              Modal.confirm({ title: "Revoke this permission?", onOk: () => onRevoke(row) })
            }
          />
        </Tooltip>
      ),
    },
  ];

  const [principalType, setPrincipalType] = useState<"user" | "group">("group");

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>Permissions</Typography.Title>

        <Radio.Group value={resourceType} onChange={(e) => setResourceType(e.target.value)}>
          <Radio.Button value="database">Database</Radio.Button>
          <Radio.Button value="layer">Layer</Radio.Button>
        </Radio.Group>

        <Select
          placeholder="Select database"
          style={{ width: 200 }}
          value={selectedDbId || undefined}
          options={databases.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(v) => { setSelectedDbId(v); setSelectedLayerId(""); }}
        />

        {resourceType === "layer" && selectedDbId && (
          <Select
            placeholder="Select layer"
            style={{ width: 220 }}
            value={selectedLayerId || undefined}
            options={layers.map((l) => ({ value: l.id, label: l.name }))}
            onChange={setSelectedLayerId}
          />
        )}

        {resourceId && (
          <Button icon={<PlusOutlined />} type="primary" onClick={() => setGrantOpen(true)}>
            Grant permission
          </Button>
        )}
      </Space>

      {!resourceId ? (
        <Typography.Text type="secondary">Select a resource above to manage its permissions.</Typography.Text>
      ) : (
        <Table rowKey="id" dataSource={permissions} columns={columns} loading={loadingPerms} />
      )}

      <Modal
        title="Grant permission"
        open={grantOpen}
        onOk={form.submit}
        onCancel={() => { setGrantOpen(false); form.resetFields(); }}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" onFinish={onGrant} initialValues={{ allow: true, principal_type: "group" }}>
          <Form.Item name="principal_type" label="Grant to">
            <Radio.Group onChange={(e) => setPrincipalType(e.target.value)}>
              <Radio.Button value="group">Group</Radio.Button>
              <Radio.Button value="user">User</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="principal_id" label={principalType === "group" ? "Group" : "User"} rules={[{ required: true }]}>
            <Select
              showSearch
              filterOption={(input, opt) =>
                (opt?.label as string ?? "").toLowerCase().includes(input.toLowerCase())
              }
              options={
                principalType === "group"
                  ? groups.map((g) => ({ value: g.id, label: g.display_name ?? g.ms_group_id }))
                  : users.map((u) => ({ value: u.id, label: u.display_name ?? u.email }))
              }
            />
          </Form.Item>

          <Form.Item name="role_id" label="Role" rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.id, label: r.name }))} />
          </Form.Item>

          <Form.Item name="allow" label="Effect">
            <Radio.Group>
              <Radio.Button value={true}>Allow</Radio.Button>
              <Radio.Button value={false}>Deny</Radio.Button>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
