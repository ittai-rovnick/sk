import { Form, Select, Switch, Button, Space, Radio } from "antd";
import type { Role } from "../../types";

interface Props {
  roles: Role[];
  onSubmit: (values: unknown) => void;
  onCancel: () => void;
  loading?: boolean;
}

export function PermissionForm({ roles, onSubmit, onCancel, loading }: Props) {
  const [form] = Form.useForm();
  const principalType = Form.useWatch("principal_type", form);

  return (
    <Form form={form} layout="vertical" onFinish={onSubmit}>
      <Form.Item name="principal_type" label="Grant to" initialValue="user">
        <Radio.Group>
          <Radio.Button value="user">User</Radio.Button>
          <Radio.Button value="group">Group</Radio.Button>
        </Radio.Group>
      </Form.Item>

      {principalType === "user" ? (
        <Form.Item name="ms_user_id" label="Microsoft User ID" rules={[{ required: true }]}>
          <Select showSearch placeholder="Search by object ID" />
        </Form.Item>
      ) : (
        <Form.Item name="ms_group_id" label="Microsoft Group ID" rules={[{ required: true }]}>
          <Select showSearch placeholder="Search by group object ID" />
        </Form.Item>
      )}

      <Form.Item name="role_id" label="Role" rules={[{ required: true }]}>
        <Select
          options={roles.map((r) => ({ value: r.id, label: r.name }))}
        />
      </Form.Item>

      <Form.Item name="allow" label="Allow" valuePropName="checked" initialValue={true}>
        <Switch checkedChildren="Allow" unCheckedChildren="Deny" />
      </Form.Item>

      <Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={loading}>
            Grant
          </Button>
          <Button onClick={onCancel}>Cancel</Button>
        </Space>
      </Form.Item>
    </Form>
  );
}
