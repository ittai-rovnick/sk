import { useState } from "react";
import { Select, Typography, Space, Drawer, Button, Empty } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { databases as dbApi } from "../api/databases";
import { groupLayers as glApi, layers as layerApi } from "../api/layers";
import { LayerTree } from "../components/layers/LayerTree";
import { LayerForm } from "../components/layers/LayerForm";
import { LockButton } from "../components/layers/LockButton";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import type { Layer } from "../types";
import { useNavigate } from "react-router-dom";

export function LayersPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [dbId, setDbId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedLayer, setSelectedLayer] = useState<Layer | null>(null);

  const { data: dbs } = useQuery({ queryKey: ["databases"], queryFn: dbApi.list });

  const { data: gls, isLoading: glLoading } = useQuery({
    queryKey: ["group-layers", dbId],
    queryFn: () => glApi.tree(dbId!),
    enabled: !!dbId,
  });

  const { data: ls, isLoading: layerLoading } = useQuery({
    queryKey: ["layers", dbId],
    queryFn: () => layerApi.list(dbId!),
    enabled: !!dbId,
  });

  const create = useMutation({
    mutationFn: (vals: Partial<Layer>) =>
      layerApi.create({ ...vals, database_id: dbId! }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["layers", dbId] });
      setDrawerOpen(false);
    },
  });

  const lock = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      layerApi.lock(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["layers", dbId] }),
  });

  const unlock = useMutation({
    mutationFn: (id: string) => layerApi.unlock(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["layers", dbId] }),
  });

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Layers
        </Typography.Title>
        <Select
          placeholder="Select database"
          style={{ width: 240 }}
          options={(dbs ?? []).map((d) => ({ value: d.id, label: d.name }))}
          onChange={setDbId}
        />
        {dbId && (
          <Button icon={<PlusOutlined />} type="primary" onClick={() => setDrawerOpen(true)}>
            New layer
          </Button>
        )}
      </Space>

      {!dbId && <Empty description="Select a database to see its layers" />}

      {dbId && (glLoading || layerLoading) && <LoadingSpinner />}

      {dbId && !glLoading && !layerLoading && (
        <Space direction="vertical" style={{ width: "100%" }}>
          <LayerTree
            groupLayers={gls ?? []}
            layers={ls ?? []}
            onSelectLayer={(layer) => navigate(`/layers/${layer.id}`)}
          />
          {selectedLayer && (
            <LockButton
              layer={selectedLayer}
              onLock={(reason) => lock.mutateAsync({ id: selectedLayer.id, reason })}
              onUnlock={() => unlock.mutateAsync(selectedLayer.id)}
            />
          )}
        </Space>
      )}

      <Drawer
        title="New layer"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={480}
      >
        <LayerForm
          onSubmit={(vals) => create.mutate(vals)}
          onCancel={() => setDrawerOpen(false)}
          loading={create.isPending}
        />
      </Drawer>
    </>
  );
}
