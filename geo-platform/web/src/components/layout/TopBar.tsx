import { Layout, Button, Space, Typography, Avatar } from "antd";
import { LogoutOutlined, UserOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";

const { Header } = Layout;

export function TopBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

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
          {user?.display_name ?? user?.email}
        </Typography.Text>
        <Button
          type="text"
          icon={<LogoutOutlined />}
          style={{ color: "#fff" }}
          onClick={handleLogout}
        >
          Sign out
        </Button>
      </Space>
    </Header>
  );
}
