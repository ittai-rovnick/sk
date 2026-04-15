import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { loginRequest } from "./msalConfig";

export function useAuth() {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const account = accounts[0] ?? null;

  const login = () => instance.loginRedirect(loginRequest);
  const logout = () =>
    instance.logoutRedirect({ postLogoutRedirectUri: window.location.origin });

  return { isAuthenticated, account, login, logout };
}
