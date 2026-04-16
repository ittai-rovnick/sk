import { Form, Input, Select, Button, Space } from "antd";
import type { Layer } from "../../types";

interface Props {
  initialValues?: Partial<Layer>;
  onSubmit: (values: Partial<Layer>) => void;
  onCancel: () => void;
  loading?: boolean;
}

export function LayerForm({ initialValues, onSubmit, onCancel, loading }: Props) {
  const [form] = Form.useForm();

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={initialValues}
      onFinish={onSubmit}
    >
      <Form.Item name="name" label="Name" rules={[{ required: true }]}>
        <Input />
      </Form.Item>

      <Form.Item name="description" label="Description">
        <Input.TextArea rows={2} />
      </Form.Item>

      <Form.Item name="tags" label="Tags">
        <Select mode="tags" placeholder="Add tags" />
      </Form.Item>

      <Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={loading}>
            Save
          </Button>
          <Button onClick={onCancel}>Cancel</Button>
        </Space>
      </Form.Item>
    </Form>
  );
}
