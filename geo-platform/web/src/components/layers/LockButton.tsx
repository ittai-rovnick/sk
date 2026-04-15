import { Button, Modal, Input, Tooltip } from "antd";
import { LockOutlined, UnlockOutlined } from "@ant-design/icons";
import { useState } from "react";
import type { Layer } from "../../types";

interface Props {
  layer: Layer;
  onLock: (reason: string) => Promise<void>;
  onUnlock: () => Promise<void>;
}

export function LockButton({ layer, onLock, onUnlock }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLock = async () => {
    setLoading(true);
    await onLock(reason);
    setLoading(false);
    setModalOpen(false);
    setReason("");
  };

  if (layer.is_locked) {
    return (
      <Tooltip title={layer.lock_reason ?? "Locked"}>
        <Button
          icon={<UnlockOutlined />}
          danger
          onClick={async () => {
            setLoading(true);
            await onUnlock();
            setLoading(false);
          }}
          loading={loading}
        >
          Unlock
        </Button>
      </Tooltip>
    );
  }

  return (
    <>
      <Button icon={<LockOutlined />} onClick={() => setModalOpen(true)}>
        Lock
      </Button>
      <Modal
        title="Lock layer"
        open={modalOpen}
        onOk={handleLock}
        onCancel={() => setModalOpen(false)}
        confirmLoading={loading}
      >
        <Input
          placeholder="Reason (optional)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Modal>
    </>
  );
}
