import { Typography } from "antd";
import { DrawMap } from "../components/shared/DrawMap";

export function MapPage() {
  return (
    <>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>Map</Typography.Title>
      <DrawMap style={{ height: "calc(100vh - 140px)" }} />
    </>
  );
}
