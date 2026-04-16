import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Form, Input, Button, Typography, Alert, Spin } from "antd";
import { UserOutlined } from "@ant-design/icons";
import client from "../api/client";
import { auth } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import type { User } from "../types";

export function LoginPage() {
  const navigate = useNavigate();
  const { setAuth } = useAuth();
  const [loading, setLoading] = useState(false);
  const [autoLoading, setAutoLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // On mount: try to detect the OS user and log in automatically
  useEffect(() => {
    client
      .get<{ token: string; user: User }>("/auth/auto-login")
      .then(({ data }) => {
        setAuth(data.token, data.user);
        navigate("/databases", { replace: true });
      })
      .catch(() => {
        // No OS match — show the manual form
        setAutoLoading(false);
      });
  }, []);

  async function onFinish({ username }: { username: string }) {
    setLoading(true);
    setError(null);
    try {
      const { token, user } = await auth.login(username);
      setAuth(token, user);
      navigate("/databases", { replace: true });
    } catch {
      setError("User not found or account inactive.");
    } finally {
      setLoading(false);
    }
  }

  if (autoLoading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin size="large" tip="Signing you in…" />
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f0f2f5",
      }}
    >
      <Card style={{ width: 380 }}>
        <Typography.Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          Geo Platform
        </Typography.Title>

        {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="username"
            label="Email"
            rules={[{ required: true, message: "Enter your email" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="you@example.com" size="large" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              Sign in
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
