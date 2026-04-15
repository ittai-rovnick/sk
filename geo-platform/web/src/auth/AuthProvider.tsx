import { MsalProvider } from "@azure/msal-react";
import { msalInstance } from "./msalConfig";

interface Props {
  children: React.ReactNode;
}

export function AuthProvider({ children }: Props) {
  return <MsalProvider instance={msalInstance}>{children}</MsalProvider>;
}
