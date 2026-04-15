import { Layout } from "antd";
import { Outlet } from "react-router-dom";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";

const { Content } = Layout;

export function AppLayout() {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <TopBar />
      <Layout>
        <Sidebar />
        <Content style={{ padding: 24, overflowY: "auto" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
