import { Layout, Button, Space, Typography, Avatar } from "antd";
import { LogoutOutlined, UserOutlined } from "@ant-design/icons";
import { useAuth } from "../../auth/useAuth";

const { Header } = Layout;

export function TopBar() {
  const { account, logout } = useAuth();

  return (
    <Header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        background: "#001529",
      }}
    >
      <Typography.Text style={{ color: "#fff", fontSize: 18, fontWeight: 600 }}>
        Geo Platform
      </Typography.Text>

      <Space>
        <Avatar icon={<UserOutlined />} />
        <Typography.Text style={{ color: "#fff" }}>
          {account?.name ?? account?.username}
        </Typography.Text>
        <Button
          type="text"
          icon={<LogoutOutlined />}
          style={{ color: "#fff" }}
          onClick={logout}
        >
          Sign out
        </Button>
      </Space>
    </Header>
  );
}
