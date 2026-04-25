/**
 * Nested AND/OR builder for the feature attribute filter DSL.
 * Outputs the same JSON shape that the backend's compile_expression() expects.
 */
import { useEffect, useState } from "react";
import {
  Card, Select, Input, InputNumber, Button, Space, Tag, Switch,
  Modal, Form, Tooltip, message, Divider,
} from "antd";
import {
  PlusOutlined, DeleteOutlined, SaveOutlined, FolderOpenOutlined,
} from "@ant-design/icons";
import type { SavedExpressionListItem } from "../../types";
import { layers } from "../../api/layers";

// ── DSL types ──────────────────────────────────────────────────────────────────

type Op =
  | "eq" | "ne" | "gt" | "gte" | "lt" | "lte"
  | "between" | "contains" | "starts_with" | "ends_with"
  | "in" | "not_in" | "is_null" | "is_not_null";

interface Condition {
  field: string;
  op: Op;
  value?: unknown;
  lo?: number; hi?: number;
}

interface Group {
  op: "AND" | "OR";
  conditions: (Group | Condition)[];
}

type Node = Group | Condition;

function isGroup(n: Node): n is Group {
  return (n as Group).op === "AND" || (n as Group).op === "OR";
}

// ── Field schema (subset of what the layer schema returns) ─────────────────────

interface SchemaField {
  name: string;
  type?: "string" | "number" | "boolean" | "date";
}

const STRING_OPS: Op[] = ["eq", "ne", "contains", "starts_with", "ends_with", "in", "not_in", "is_null", "is_not_null"];
const NUMBER_OPS: Op[] = ["eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "is_null", "is_not_null"];
const BOOLEAN_OPS: Op[] = ["eq", "is_null", "is_not_null"];

function opsForType(t?: string): Op[] {
  if (t === "number") return NUMBER_OPS;
  if (t === "boolean") return BOOLEAN_OPS;
  return STRING_OPS;
}

function defaultConditionForField(f: SchemaField): Condition {
  return { field: f.name, op: "eq", value: f.type === "boolean" ? true : (f.type === "number" ? 0 : "") };
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function emptyExpression(): Group {
  return { op: "AND", conditions: [] };
}

/** Replace the node at `path` (array of indices into nested `conditions`) with `next`. */
function replaceAt(root: Group, path: number[], next: Node | null): Group {
  if (path.length === 0) {
    // Replace the root entirely (only legal if the new node is a Group)
    if (next === null) return emptyExpression();
    if (isGroup(next)) return next;
    // wrap a stray condition in an AND group
    return { op: "AND", conditions: [next] };
  }
  function recurse(n: Group, p: number[]): Group {
    const idx = p[0];
    const rest = p.slice(1);
    const newChildren = [...n.conditions];
    if (rest.length === 0) {
      if (next === null) {
        newChildren.splice(idx, 1);
      } else {
        newChildren[idx] = next;
      }
    } else {
      const child = newChildren[idx];
      if (!child || !isGroup(child)) return n;
      newChildren[idx] = recurse(child, rest);
    }
    return { ...n, conditions: newChildren };
  }
  return recurse(root, path);
}

function appendAt(root: Group, path: number[], child: Node): Group {
  function recurse(n: Group, p: number[]): Group {
    if (p.length === 0) {
      return { ...n, conditions: [...n.conditions, child] };
    }
    const idx = p[0];
    const rest = p.slice(1);
    const newChildren = [...n.conditions];
    const existing = newChildren[idx];
    if (!existing || !isGroup(existing)) return n;
    newChildren[idx] = recurse(existing, rest);
    return { ...n, conditions: newChildren };
  }
  return recurse(root, path);
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface Props {
  layerId: string;
  schema: { fields?: SchemaField[] } | null;
  value: Group | null;
  onChange: (next: Group | null) => void;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function ExpressionBuilder({ layerId, schema, value, onChange }: Props) {
  const fields: SchemaField[] = schema?.fields ?? [];
  const expr = value ?? emptyExpression();

  const [savedList, setSavedList] = useState<SavedExpressionListItem[]>([]);
  const [loadOpen, setLoadOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveForm] = Form.useForm<{ name: string; description?: string }>();

  useEffect(() => {
    layers.expressions.list(layerId).then(setSavedList).catch(() => setSavedList([]));
  }, [layerId]);

  // ── Mutators ──────────────────────────────────────────────────────────────
  function setRoot(next: Group) { onChange(next); }

  function updateNode(path: number[], next: Node | null) {
    setRoot(replaceAt(expr, path, next));
  }

  function addCondition(path: number[]) {
    if (fields.length === 0) {
      message.warning("No fields defined in the layer schema.");
      return;
    }
    setRoot(appendAt(expr, path, defaultConditionForField(fields[0])));
  }

  function addGroup(path: number[]) {
    setRoot(appendAt(expr, path, { op: "AND", conditions: [] }));
  }

  // ── Save / Load ────────────────────────────────────────────────────────────
  async function submitSave(values: { name: string; description?: string }) {
    try {
      await layers.expressions.create(layerId, {
        name: values.name,
        description: values.description,
        expression: expr,
      });
      const list = await layers.expressions.list(layerId);
      setSavedList(list);
      setSaveOpen(false);
      saveForm.resetFields();
      message.success(`Saved "${values.name}"`);
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? "Failed to save — expression may be invalid";
      message.error(msg);
    }
  }

  async function loadSaved(id: string) {
    try {
      const detail = await layers.expressions.get(layerId, id);
      // Trust the saved expression matches our shape
      onChange(detail.expression as unknown as Group);
      setLoadOpen(false);
    } catch {
      message.error("Failed to load expression");
    }
  }

  // ── Render a single condition ──────────────────────────────────────────────
  function renderCondition(cond: Condition, path: number[]) {
    const field = fields.find((f) => f.name === cond.field);
    const ops = opsForType(field?.type);

    function patch(part: Partial<Condition>) {
      updateNode(path, { ...cond, ...part });
    }

    function onFieldChange(name: string) {
      const f = fields.find((x) => x.name === name);
      if (!f) return;
      // Reset op/value to defaults appropriate for the new type
      const allowed = opsForType(f.type);
      const op = allowed.includes(cond.op) ? cond.op : allowed[0];
      patch({ field: name, op, value: f.type === "boolean" ? true : (f.type === "number" ? 0 : "") });
    }

    const showsValue = cond.op !== "is_null" && cond.op !== "is_not_null" && cond.op !== "between";
    const showsRange = cond.op === "between";
    const isList = cond.op === "in" || cond.op === "not_in";

    return (
      <Space wrap size={6}>
        <Select
          size="small"
          style={{ minWidth: 130 }}
          value={cond.field}
          options={fields.map((f) => ({ value: f.name, label: f.name }))}
          onChange={onFieldChange}
          showSearch
          placeholder="field"
        />
        <Select
          size="small"
          style={{ minWidth: 100 }}
          value={cond.op}
          options={ops.map((o) => ({ value: o, label: o }))}
          onChange={(o: Op) => patch({ op: o, value: undefined })}
        />
        {showsValue && !isList && field?.type === "boolean" && (
          <Switch
            checked={cond.value === true}
            onChange={(b) => patch({ value: b })}
          />
        )}
        {showsValue && !isList && field?.type === "number" && (
          <InputNumber
            size="small"
            value={cond.value as number | undefined}
            onChange={(n) => patch({ value: n ?? 0 })}
          />
        )}
        {showsValue && !isList && (field?.type !== "boolean" && field?.type !== "number") && (
          <Input
            size="small"
            style={{ minWidth: 140 }}
            value={(cond.value as string) ?? ""}
            onChange={(e) => patch({ value: e.target.value })}
            placeholder="value"
          />
        )}
        {isList && (
          <Select
            size="small"
            mode="tags"
            style={{ minWidth: 200 }}
            value={Array.isArray(cond.value) ? (cond.value as string[]) : []}
            onChange={(vals) => patch({ value: vals })}
            placeholder="values (Enter to add)"
            tokenSeparators={[","]}
          />
        )}
        {showsRange && (
          <Space size={4}>
            <InputNumber
              size="small"
              placeholder="lo"
              value={cond.lo}
              onChange={(n) => patch({ lo: n ?? 0 })}
            />
            <span>—</span>
            <InputNumber
              size="small"
              placeholder="hi"
              value={cond.hi}
              onChange={(n) => patch({ hi: n ?? 0 })}
            />
          </Space>
        )}
        <Tooltip title="Remove">
          <Button
            size="small" type="text" danger
            icon={<DeleteOutlined />}
            onClick={() => updateNode(path, null)}
          />
        </Tooltip>
      </Space>
    );
  }

  // ── Render a group ─────────────────────────────────────────────────────────
  function renderGroup(group: Group, path: number[]): JSX.Element {
    const isRoot = path.length === 0;
    return (
      <Card
        size="small"
        bodyStyle={{ padding: 8 }}
        style={{ background: isRoot ? "#fafafa" : "#fff", marginBottom: 6 }}
      >
        <Space wrap style={{ marginBottom: 8 }}>
          <Tag color={group.op === "AND" ? "blue" : "purple"} style={{ marginRight: 0 }}>
            {group.op}
          </Tag>
          <Select
            size="small"
            style={{ width: 80 }}
            value={group.op}
            options={[{ value: "AND", label: "AND" }, { value: "OR", label: "OR" }]}
            onChange={(op: "AND" | "OR") => updateNode(path, { ...group, op })}
          />
          <Button size="small" icon={<PlusOutlined />} onClick={() => addCondition(path)}>
            Condition
          </Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => addGroup(path)}>
            Group
          </Button>
          {!isRoot && (
            <Tooltip title="Remove this group">
              <Button
                size="small" type="text" danger
                icon={<DeleteOutlined />}
                onClick={() => updateNode(path, null)}
              />
            </Tooltip>
          )}
        </Space>

        {group.conditions.length === 0 && (
          <div style={{ color: "#8c8c8c", fontSize: 12, padding: 4 }}>
            Empty — add a condition or sub-group.
          </div>
        )}

        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          {group.conditions.map((c, i) => {
            const childPath = [...path, i];
            return (
              <div key={i} style={{ paddingLeft: isGroup(c) ? 0 : 4 }}>
                {isGroup(c) ? renderGroup(c, childPath) : renderCondition(c, childPath)}
              </div>
            );
          })}
        </Space>
      </Card>
    );
  }

  // ── Top-level ──────────────────────────────────────────────────────────────
  return (
    <div>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button size="small" icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>
          Save as…
        </Button>
        <Button size="small" icon={<FolderOpenOutlined />} onClick={() => setLoadOpen(true)}>
          Load saved
        </Button>
        <Button size="small" danger onClick={() => onChange(null)}>
          Clear
        </Button>
      </Space>

      {renderGroup(expr, [])}

      <Modal
        title="Save expression"
        open={saveOpen}
        onOk={saveForm.submit}
        onCancel={() => setSaveOpen(false)}
        destroyOnClose
      >
        <Form form={saveForm} layout="vertical" onFinish={submitSave}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Load saved expression"
        open={loadOpen}
        onCancel={() => setLoadOpen(false)}
        footer={null}
        destroyOnClose
      >
        {savedList.length === 0 ? (
          <div style={{ color: "#8c8c8c" }}>No saved expressions for this layer.</div>
        ) : (
          <Space direction="vertical" style={{ width: "100%" }}>
            {savedList.map((s) => (
              <Card
                key={s.id}
                size="small"
                hoverable
                onClick={() => loadSaved(s.id)}
                style={{ cursor: "pointer" }}
              >
                <Space direction="vertical" size={2}>
                  <strong>{s.name}</strong>
                  {s.description && (
                    <span style={{ fontSize: 12, color: "#595959" }}>{s.description}</span>
                  )}
                  <span style={{ fontSize: 11, color: "#8c8c8c" }}>
                    {new Date(s.created_at).toLocaleString()}
                  </span>
                </Space>
              </Card>
            ))}
            <Divider style={{ margin: "8px 0" }} />
            <span style={{ fontSize: 11, color: "#8c8c8c" }}>Click a row to load.</span>
          </Space>
        )}
      </Modal>
    </div>
  );
}
