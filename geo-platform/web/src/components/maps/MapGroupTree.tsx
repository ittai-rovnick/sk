import { useMemo, useState } from "react";
import {
  Tree, Dropdown, Button, Space, Tag, Tooltip,
  Modal, Form, Input, message,
} from "antd";
import {
  FolderOutlined, FolderOpenOutlined,
  EnvironmentOutlined, EyeOutlined, EyeInvisibleOutlined,
  MoreOutlined, DownloadOutlined,
  PlusOutlined, EditOutlined, DeleteOutlined, SafetyOutlined,
} from "@ant-design/icons";
import type { DataNode } from "antd/es/tree";
import type { MapTreeNode, MapGroupNode, MapLayerNode } from "../../types";
import { mapsApi, downloadLayerExport } from "../../api/maps";

interface Props {
  tree: MapTreeNode[];
  mapId: string;
  onRefresh: () => void;
  onGrantPermissions?: (groupId: string, groupName: string) => void;
  onLayerClick?: (node: MapLayerNode) => void;
}

const GEOM_ICON_COLOR: Record<string, string> = {
  POINT: "#1677ff",
  MULTIPOINT: "#1677ff",
  LINESTRING: "#52c41a",
  MULTILINESTRING: "#52c41a",
  POLYGON: "#fa8c16",
  MULTIPOLYGON: "#fa8c16",
};

function geomColor(types: string[]): string {
  for (const t of types) {
    const c = GEOM_ICON_COLOR[t.toUpperCase()];
    if (c) return c;
  }
  return "#8c8c8c";
}

export function MapGroupTree({ tree, mapId, onRefresh, onGrantPermissions, onLayerClick }: Props) {
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<{ id: string; name: string } | null>(null);
  const [renameForm] = Form.useForm<{ name: string }>();

  const [addSubOpen, setAddSubOpen] = useState(false);
  const [addSubParent, setAddSubParent] = useState<string | null>(null);
  const [addSubForm] = Form.useForm<{ name: string }>();

  // ── Layer actions ──────────────────────────────────────────────────────────
  async function toggleVisible(node: MapLayerNode) {
    try {
      await mapsApi.updateLayer(mapId, node.layer_id, { is_visible: !node.is_visible });
      onRefresh();
    } catch {
      message.error("Failed to update visibility");
    }
  }

  async function removeLayer(node: MapLayerNode) {
    Modal.confirm({
      title: `Remove "${node.name}" from this map?`,
      content: "The layer itself is not deleted.",
      okText: "Remove",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await mapsApi.removeLayer(mapId, node.layer_id);
          onRefresh();
        } catch {
          message.error("Failed to remove layer");
        }
      },
    });
  }

  async function exportLayer(node: MapLayerNode, format: "geojson" | "shapefile" | "gpkg") {
    try {
      await downloadLayerExport(node.layer_id, format, undefined, `${node.name}.${format === "shapefile" ? "zip" : format}`);
    } catch {
      message.error(`Export failed: ${format}`);
    }
  }

  // ── Group actions ──────────────────────────────────────────────────────────
  function openRename(group: MapGroupNode) {
    setRenameTarget({ id: group.id, name: group.name });
    renameForm.setFieldsValue({ name: group.name });
    setRenameOpen(true);
  }

  async function submitRename(values: { name: string }) {
    if (!renameTarget) return;
    try {
      await mapsApi.updateGroup(mapId, renameTarget.id, { name: values.name });
      setRenameOpen(false);
      onRefresh();
    } catch {
      message.error("Failed to rename group");
    }
  }

  function openAddSub(parentGroupId: string | null) {
    setAddSubParent(parentGroupId);
    addSubForm.resetFields();
    setAddSubOpen(true);
  }

  async function submitAddSub(values: { name: string }) {
    try {
      await mapsApi.createGroup(mapId, { name: values.name, parent_id: addSubParent });
      setAddSubOpen(false);
      onRefresh();
    } catch {
      message.error("Failed to create group");
    }
  }

  function deleteGroup(group: MapGroupNode) {
    Modal.confirm({
      title: `Delete group "${group.name}"?`,
      content: "Sub-groups stay; layers move to the map root.",
      okText: "Delete",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await mapsApi.deleteGroup(mapId, group.id);
          onRefresh();
        } catch {
          message.error("Failed to delete group");
        }
      },
    });
  }

  // ── Convert tree → AntD Tree DataNode ──────────────────────────────────────
  const dataNodes: DataNode[] = useMemo(() => {
    function toLayerNode(n: MapLayerNode): DataNode {
      const color = geomColor(n.geometry_types);
      return {
        key: `layer:${n.map_layer_id}`,
        title: (
          <Space size={6} style={{ width: "100%", justifyContent: "space-between" }}>
            <Space size={6} style={{ flex: 1, minWidth: 0 }}>
              <EnvironmentOutlined style={{ color }} />
              <span
                title={n.name}
                onClick={(e) => { e.stopPropagation(); onLayerClick?.(n); }}
                style={{
                  cursor: onLayerClick ? "pointer" : "default",
                  opacity: n.is_visible ? 1 : 0.5,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                  maxWidth: 160,
                }}
              >
                {n.name}
              </span>
              {n.geometry_types.length === 0 && <Tag color="default" style={{ fontSize: 10 }}>empty</Tag>}
            </Space>
            <Space size={2} onClick={(e) => e.stopPropagation()}>
              <Tooltip title={n.is_visible ? "Hide" : "Show"}>
                <Button
                  size="small" type="text"
                  icon={n.is_visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                  onClick={() => toggleVisible(n)}
                />
              </Tooltip>
              <Dropdown
                menu={{
                  items: [
                    { key: "geojson",   label: "GeoJSON",     onClick: () => exportLayer(n, "geojson") },
                    { key: "shapefile", label: "Shapefile",   onClick: () => exportLayer(n, "shapefile") },
                    { key: "gpkg",      label: "GeoPackage",  onClick: () => exportLayer(n, "gpkg") },
                  ],
                }}
                trigger={["click"]}
              >
                <Tooltip title="Export">
                  <Button size="small" type="text" icon={<DownloadOutlined />} />
                </Tooltip>
              </Dropdown>
              <Dropdown
                menu={{
                  items: [
                    { key: "remove", label: "Remove from map", danger: true,
                      icon: <DeleteOutlined />, onClick: () => removeLayer(n) },
                  ],
                }}
                trigger={["click"]}
              >
                <Button size="small" type="text" icon={<MoreOutlined />} />
              </Dropdown>
            </Space>
          </Space>
        ),
        isLeaf: true,
      };
    }

    function toGroupNode(n: MapGroupNode): DataNode {
      const Icon = n.is_expanded ? FolderOpenOutlined : FolderOutlined;
      return {
        key: `group:${n.id}`,
        title: (
          <Space size={6} style={{ width: "100%", justifyContent: "space-between" }}>
            <Space size={6} style={{ flex: 1, minWidth: 0 }}>
              <Icon />
              <span
                title={n.name}
                style={{
                  fontWeight: 500,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                  maxWidth: 180,
                }}
              >
                {n.name}
              </span>
              {n.embedded_map_id && <Tag color="purple" style={{ fontSize: 10 }}>embedded</Tag>}
            </Space>
            <span onClick={(e) => e.stopPropagation()}>
              <Dropdown
                menu={{
                  items: [
                    { key: "add",    icon: <PlusOutlined />,   label: "Add sub-group", onClick: () => openAddSub(n.id) },
                    { key: "rename", icon: <EditOutlined />,   label: "Rename",        onClick: () => openRename(n) },
                    ...(onGrantPermissions ? [{
                      key: "perms",
                      icon: <SafetyOutlined />,
                      label: "Grant permissions",
                      onClick: () => onGrantPermissions(n.id, n.name),
                    }] : []),
                    { type: "divider" as const },
                    { key: "delete", icon: <DeleteOutlined />, label: "Delete", danger: true,
                      onClick: () => deleteGroup(n) },
                  ],
                }}
                trigger={["click"]}
              >
                <Button size="small" type="text" icon={<MoreOutlined />} />
              </Dropdown>
            </span>
          </Space>
        ),
        children: n.children.map((c) =>
          c.type === "group" ? toGroupNode(c) : toLayerNode(c)
        ),
      };
    }

    return tree.map((n) =>
      n.type === "group" ? toGroupNode(n) : toLayerNode(n)
    );
  }, [tree, mapId, onLayerClick, onGrantPermissions]);

  // ── Drag-and-drop (reorder + reparent) ─────────────────────────────────────
  async function onDrop(info: Parameters<NonNullable<React.ComponentProps<typeof Tree>["onDrop"]>>[0]) {
    const dragKey = String(info.dragNode.key);
    const dropKey = String(info.node.key);
    const dropPos = info.node.pos.split("-");
    const dropPosition = info.dropPosition - Number(dropPos[dropPos.length - 1]);

    const [dragKind, dragId] = dragKey.split(":");
    const [dropKind, dropId] = dropKey.split(":");

    // Only support reparenting layers (most common). Group reparent isn't universally safe.
    if (dragKind !== "layer") {
      message.info("Drag-reorder for groups not yet wired — use the menu.");
      return;
    }

    // Determine new parent group_id
    let newGroupId: string | null = null;
    if (dropPosition === 0 && dropKind === "group") {
      // dropped INTO the group
      newGroupId = dropId;
    } else {
      // dropped before/after a sibling — siblings of a group node share that group's parent
      // Walk up the tree to find the parent group
      function findParent(nodes: MapTreeNode[], targetKey: string, currentParent: string | null): string | null | undefined {
        for (const n of nodes) {
          const k = n.type === "group" ? `group:${n.id}` : `layer:${n.map_layer_id}`;
          if (k === targetKey) return currentParent;
          if (n.type === "group") {
            const found = findParent(n.children, targetKey, n.id);
            if (found !== undefined) return found;
          }
        }
        return undefined;
      }
      const parent = findParent(tree, dropKey, null);
      newGroupId = parent ?? null;
    }

    // Find the dragged map_layer's layer_id (we need it for the URL)
    function findLayer(nodes: MapTreeNode[]): MapLayerNode | null {
      for (const n of nodes) {
        if (n.type === "layer" && n.map_layer_id === dragId) return n;
        if (n.type === "group") {
          const f = findLayer(n.children);
          if (f) return f;
        }
      }
      return null;
    }
    const layerNode = findLayer(tree);
    if (!layerNode) return;

    try {
      await mapsApi.updateLayer(mapId, layerNode.layer_id, { group_id: newGroupId });
      onRefresh();
    } catch {
      message.error("Failed to move layer");
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (dataNodes.length === 0) {
    return (
      <div style={{ padding: "24px 0", textAlign: "center", color: "#8c8c8c" }}>
        <Space direction="vertical">
          <span>No layers in this map.</span>
          <Button size="small" icon={<PlusOutlined />} onClick={() => openAddSub(null)}>
            Add a group
          </Button>
        </Space>
      </div>
    );
  }

  return (
    <>
      <Space style={{ marginBottom: 8 }}>
        <Button size="small" icon={<PlusOutlined />} onClick={() => openAddSub(null)}>
          Add group
        </Button>
      </Space>

      <Tree
        treeData={dataNodes}
        defaultExpandAll
        draggable={{ icon: false }}
        blockNode
        onDrop={onDrop}
      />

      <Modal
        title="Rename group"
        open={renameOpen}
        onOk={renameForm.submit}
        onCancel={() => setRenameOpen(false)}
        destroyOnClose
      >
        <Form form={renameForm} layout="vertical" onFinish={submitRename}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={addSubParent ? "New sub-group" : "New top-level group"}
        open={addSubOpen}
        onOk={addSubForm.submit}
        onCancel={() => setAddSubOpen(false)}
        destroyOnClose
      >
        <Form form={addSubForm} layout="vertical" onFinish={submitAddSub}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
