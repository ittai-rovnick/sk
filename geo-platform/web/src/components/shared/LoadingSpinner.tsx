import { Flex, Spin } from "antd";

export function LoadingSpinner() {
  return (
    <Flex justify="center" align="center" style={{ height: "100%" }}>
      <Spin size="large" />
    </Flex>
  );
}
