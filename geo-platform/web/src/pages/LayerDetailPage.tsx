import { Tabs, Descriptions, Tag, Typography, Space } from "antd";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { layers as layerApi } from "../api/layers";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";

export function LayerDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: layer, isLoading } = useQuery({
    queryKey: ["layer", id],
    queryFn: () => layerApi.get(id!),
    enabled: !!id,
  });

  if (isLoading) return <LoadingSpinner />;
  if (!layer) return null;

  const items = [
    { key: "meta", label: "Metadata", children: (
      <Descriptions bordered column={2}>
        <Descriptions.Item label="ID">{layer.id}</Descriptions.Item>
        <Descriptions.Item label="Geometry type">{layer.geometry_type}</Descriptions.Item>
        <Descriptions.Item label="SRID">{layer.srid}</Descriptions.Item>
        <Descriptions.Item label="Shard">{layer.shard_id}</Descriptions.Item>
        <Descriptions.Item label="Status">
          <Tag color={layer.status === "published" ? "green" : "default"}>{layer.status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Health">
          <Tag color={layer.health === "ok" ? "green" : "red"}>{layer.health}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Locked">
          {layer.is_locked ? <Tag color="orange">Locked — {layer.lock_reason}</Tag> : "No"}
        </Descriptions.Item>
        <Descriptions.Item label="Tags">
          {layer.tags.map((t) => <Tag key={t}>{t}</Tag>)}
        </Descriptions.Item>
        <Descriptions.Item label="Created">{new Date(layer.created_at).toLocaleString()}</Descriptions.Item>
        <Descriptions.Item label="Updated">{new Date(layer.updated_at).toLocaleString()}</Descriptions.Item>
      </Descriptions>
    )},
    { key: "schema", label: "Schema", children: <pre>{JSON.stringify({}, null, 2)}</pre> },
    { key: "style", label: "Style", children: <Typography.Text type="secondary">No styles yet.</Typography.Text> },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>{layer.name}</Typography.Title>
        {layer.description && (
          <Typography.Text type="secondary">{layer.description}</Typography.Text>
        )}
      </Space>
      <Tabs items={items} />
    </>
  );
}
