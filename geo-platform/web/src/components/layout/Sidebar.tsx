import { Layout, Menu } from "antd";
import {
  DatabaseOutlined,
  ApartmentOutlined,
  SafetyOutlined,
  TeamOutlined,
  UserOutlined,
  FileTextOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";

const { Sider } = Layout;

const menuItems = [
  { key: "/databases", icon: <DatabaseOutlined />, label: "Databases" },
  { key: "/layers", icon: <ApartmentOutlined />, label: "Layers" },
  { key: "/permissions", icon: <SafetyOutlined />, label: "Permissions" },
  { key: "/users", icon: <UserOutlined />, label: "Users" },
  { key: "/groups", icon: <TeamOutlined />, label: "Groups" },
  { key: "/audit", icon: <FileTextOutlined />, label: "Audit Log" },
  { key: "/conflicts", icon: <WarningOutlined />, label: "Sync Conflicts" },
];

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Sider width={220} style={{ background: "#001529" }}>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
        style={{ marginTop: 16 }}
      />
    </Sider>
  );
}
