import { useState, useEffect, useMemo } from "react";
import {
  Tree, Button, Typography, Space, Modal, Form, Input, message,
  Card, Empty, Breadcrumb, Popconfirm, Tag,
} from "antd";
import type { DataNode, TreeProps } from "antd/es/tree";
import { PlusOutlined, DeleteOutlined, TeamOutlined } from "@ant-design/icons";
import client from "../api/client";

interface Group {
  id: string;
  ms_group_id: string;
  display_name: string | null;
  description: string | null;
  is_custom: boolean;
  parent_group_id: string | null;
  created_at: string;
}

interface GroupTreeNode {
  id: string;
  ms_group_id: string;
  display_name: string | null;
  description: string | null;
  parent_group_id: string | null;
  children: GroupTreeNode[];
}

interface Member {
  user_id: string;
  email: string;
  display_name: string | null;
  added_at: string;
}

function toDataNodes(nodes: GroupTreeNode[]): DataNode[] {
  return nodes.map((n) => ({
    key: n.id,
    title: (
      <span>
        <TeamOutlined style={{ marginRight: 6, color: "#60a5fa" }} />
        {n.display_name || "(unnamed)"}
      </span>
    ),
    children: n.children.length > 0 ? toDataNodes(n.children) : undefined,
  }));
}

function findGroup(tree: GroupTreeNode[], id: string): GroupTreeNode | null {
  for (const n of tree) {
    if (n.id === id) return n;
    const found = findGroup(n.children, id);
    if (found) return found;
  }
  return null;
}

function getAllIds(tree: GroupTreeNode[]): string[] {
  const ids: string[] = [];
  const walk = (nodes: GroupTreeNode[]) => {
    for (const n of nodes) {
      ids.push(n.id);
      walk(n.children);
    }
  };
  walk(tree);
  return ids;
}

export function GroupsPage() {
  const [tree, setTree] = useState<GroupTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [createUnderId, setCreateUnderId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const [ancestors, setAncestors] = useState<Group[]>([]);
  const [members, setMembers] = useState<Member[]>([]);

  async function load() {
    setLoading(true);
    try {
      const r = await client.get<GroupTreeNode[]>("/groups/tree");
      setTree(r.data);
      setExpanded(getAllIds(r.data));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!selectedId) {
      setAncestors([]);
      setMembers([]);
      return;
    }
    client.get<Group[]>(`/groups/${selectedId}/ancestors`).then((r) => setAncestors(r.data));
    client.get<Member[]>(`/groups/${selectedId}/members`).then((r) => setMembers(r.data));
  }, [selectedId]);

  const selectedGroup = useMemo(
    () => (selectedId ? findGroup(tree, selectedId) : null),
    [tree, selectedId]
  );

  const treeData = useMemo(() => toDataNodes(tree), [tree]);

  function openCreate(underId: string | null) {
    setCreateUnderId(underId);
    setModalOpen(true);
  }

  async function onCreate(values: { display_name: string; description?: string }) {
    setSaving(true);
    try {
      await client.post("/groups", { ...values, parent_group_id: createUnderId });
      message.success(createUnderId ? "Sub-group created" : "Group created");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch {
      message.error("Failed to create group");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: string) {
    try {
      await client.delete(`/groups/${id}`);
      message.success("Group deleted");
      if (selectedId === id) setSelectedId(null);
      load();
    } catch {
      message.error("Failed to delete group");
    }
  }

  const onDrop: TreeProps["onDrop"] = async (info) => {
    const dragId = info.dragNode.key as string;
    const dropId = info.node.key as string;
    const dropToGap = info.dropToGap;

    // Determine new parent: dropping on a node → parent = that node;
    // dropping between nodes (gap) → parent = drop target's parent.
    let newParentId: string | null = null;
    if (dropToGap) {
      const target = findGroup(tree, dropId);
      newParentId = target?.parent_group_id ?? null;
    } else {
      newParentId = dropId;
    }

    try {
      await client.patch(`/groups/${dragId}/move`, { parent_group_id: newParentId });
      message.success("Moved");
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "Move failed");
    }
  };

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Groups</Typography.Title>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => openCreate(null)}>
          New root group
        </Button>
      </Space>

      <div style={{ display: "flex", gap: 16 }}>
        <Card
          style={{ width: 360, flexShrink: 0 }}
          styles={{ body: { padding: 12 } }}
          loading={loading}
        >
          {tree.length === 0 ? (
            <Empty description="No groups yet" />
          ) : (
            <Tree
              treeData={treeData}
              draggable
              blockNode
              expandedKeys={expanded}
              onExpand={(keys) => setExpanded(keys as string[])}
              selectedKeys={selectedId ? [selectedId] : []}
              onSelect={(keys) => setSelectedId((keys[0] as string) ?? null)}
              onDrop={onDrop}
            />
          )}
        </Card>

        <Card style={{ flex: 1 }} styles={{ body: { padding: 20 } }}>
          {!selectedGroup ? (
            <Empty description="Select a group to see its details" />
          ) : (
            <>
              {ancestors.length > 0 && (
                <Breadcrumb
                  style={{ marginBottom: 12 }}
                  items={[
                    ...[...ancestors].reverse().map((a) => ({
                      title: (
                        <a onClick={() => setSelectedId(a.id)}>
                          {a.display_name || "(unnamed)"}
                        </a>
                      ),
                    })),
                    { title: <strong>{selectedGroup.display_name || "(unnamed)"}</strong> },
                  ]}
                />
              )}

              <Space style={{ marginBottom: 16 }} align="center">
                <Typography.Title level={4} style={{ margin: 0 }}>
                  {selectedGroup.display_name || "(unnamed)"}
                </Typography.Title>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => openCreate(selectedGroup.id)}
                >
                  Add sub-group
                </Button>
                <Popconfirm
                  title="Delete this group?"
                  description="Children become root groups. Permissions are removed."
                  onConfirm={() => onDelete(selectedGroup.id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>Delete</Button>
                </Popconfirm>
              </Space>

              {selectedGroup.description && (
                <Typography.Paragraph type="secondary">
                  {selectedGroup.description}
                </Typography.Paragraph>
              )}

              <div style={{ marginTop: 24 }}>
                <Typography.Text strong>Members ({members.length})</Typography.Text>
                <div style={{ marginTop: 8 }}>
                  {members.length === 0 ? (
                    <Typography.Text type="secondary">No direct members</Typography.Text>
                  ) : (
                    members.map((m) => (
                      <Tag key={m.user_id} style={{ marginBottom: 4 }}>
                        {m.display_name || m.email}
                      </Tag>
                    ))
                  )}
                </div>
              </div>

              <div style={{ marginTop: 24 }}>
                <Typography.Text strong>Sub-groups ({selectedGroup.children.length})</Typography.Text>
                <div style={{ marginTop: 8 }}>
                  {selectedGroup.children.length === 0 ? (
                    <Typography.Text type="secondary">No sub-groups</Typography.Text>
                  ) : (
                    selectedGroup.children.map((c) => (
                      <Tag key={c.id} color="blue" style={{ cursor: "pointer" }} onClick={() => setSelectedId(c.id)}>
                        {c.display_name || "(unnamed)"}
                      </Tag>
                    ))
                  )}
                </div>
              </div>

              <Typography.Paragraph type="secondary" style={{ fontSize: 11, marginTop: 24 }}>
                Tip: drag a group onto another to re-parent it, or between siblings to move it there.
                Members of sub-groups automatically inherit this group's permissions.
              </Typography.Paragraph>
            </>
          )}
        </Card>
      </div>

      <Modal
        title={createUnderId ? "Create sub-group" : "Create root group"}
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
