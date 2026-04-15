import { useState } from "react";
import { Button, Drawer, Typography, Space } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { permissions as permApi } from "../api/permissions";
import { PermissionMatrix } from "../components/permissions/PermissionMatrix";
import { PermissionForm } from "../components/permissions/PermissionForm";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";

// Built-in role stubs — replaced by real API data in Phase 4
const PLACEHOLDER_ROLES = [
  { id: "", name: "viewer", description: "Read only", can_read: true, can_write: false, can_delete: false, can_export: false, can_manage_style: false, can_manage_perms: false, can_publish: false },
];

export function PermissionsPage() {
  const qc = useQueryClient();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["permissions"],
    queryFn: () => permApi.list({}),
  });

  const revoke = useMutation({
    mutationFn: permApi.revoke,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });

  const grant = useMutation({
    mutationFn: permApi.grant,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["permissions"] });
      setDrawerOpen(false);
    },
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Permissions</Typography.Title>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setDrawerOpen(true)}>
          Grant permission
        </Button>
      </Space>

      <PermissionMatrix
        permissions={data ?? []}
        roles={PLACEHOLDER_ROLES}
        onRevoke={revoke.mutate}
      />

      <Drawer title="Grant permission" open={drawerOpen} onClose={() => setDrawerOpen(false)} width={480}>
        <PermissionForm
          roles={PLACEHOLDER_ROLES}
          onSubmit={grant.mutate}
          onCancel={() => setDrawerOpen(false)}
          loading={grant.isPending}
        />
      </Drawer>
    </>
  );
}
