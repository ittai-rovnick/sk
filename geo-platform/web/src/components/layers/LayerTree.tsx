import { Tree, Tag, Space } from "antd";
import { ApartmentOutlined, LockOutlined } from "@ant-design/icons";
import type { GroupLayer, Layer } from "../../types";

interface Props {
  groupLayers: GroupLayer[];
  layers: Layer[];
  onSelectLayer: (layer: Layer) => void;
}

function buildTreeData(
  groupLayers: GroupLayer[],
  layers: Layer[],
  parentId: string | null = null
): object[] {
  const groups = groupLayers
    .filter((g) => g.parent_id === parentId)
    .map((g) => ({
      key: `group-${g.id}`,
      title: (
        <Space>
          <ApartmentOutlined />
          {g.name}
        </Space>
      ),
      children: [
        ...buildTreeData(groupLayers, layers, g.id),
        ...layers
          .filter((l) => l.group_layer_id === g.id)
          .map((l) => layerNode(l)),
      ],
    }));

  const rootLayers = parentId === null
    ? layers.filter((l) => l.group_layer_id === null).map(layerNode)
    : [];

  return [...groups, ...rootLayers];
}

function layerNode(layer: Layer) {
  return {
    key: `layer-${layer.id}`,
    isLeaf: true,
    title: (
      <Space>
        {layer.name}
        <Tag color={layer.status === "published" ? "green" : layer.status === "review" ? "orange" : "default"}>
          {layer.status}
        </Tag>
        {layer.is_locked && <LockOutlined style={{ color: "#faad14" }} />}
      </Space>
    ),
  };
}

export function LayerTree({ groupLayers, layers, onSelectLayer }: Props) {
  const treeData = buildTreeData(groupLayers, layers);

  return (
    <Tree
      treeData={treeData}
      showLine
      onSelect={(keys) => {
        const key = keys[0] as string;
        if (key?.startsWith("layer-")) {
          const layerId = key.replace("layer-", "");
          const layer = layers.find((l) => l.id === layerId);
          if (layer) onSelectLayer(layer);
        }
      }}
    />
  );
}
