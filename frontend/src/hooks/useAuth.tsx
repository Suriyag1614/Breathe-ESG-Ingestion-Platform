import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { authApi, tokenStore, type User, type Tenant } from "../lib/api";

interface AuthState {
  user: User | null;
  activeTenant: { tenant: Tenant; role: string } | null;
  tenants: Array<{ tenant: Tenant; role: string }>;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<{ tenant: Tenant; role: string } | null>; // Explicit return type
  logout: () => void;
  setActiveTenant: (slug: string) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Array<{ tenant: Tenant; role: string }>>([]);
  const [activeTenant, setActiveTenantState] = useState<{ tenant: Tenant; role: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) { setIsLoading(false); return; }

    Promise.all([authApi.me(), authApi.myTenants()])
      .then(([me, myTenants]) => {
        setUser(me);
        setTenants(myTenants);
        // Restore last active tenant
        const saved = localStorage.getItem("active_tenant");
        const found = myTenants.find((m) => m.tenant.slug === saved) ?? myTenants[0] ?? null;
        setActiveTenantState(found);
      })
      .catch(() => tokenStore.clear())
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string): Promise<{ tenant: Tenant; role: string } | null> => {
    const data = await authApi.login(email, password);
    tokenStore.set(data.access);
    tokenStore.setRefresh(data.refresh);

    const myTenants = await authApi.myTenants();
    setUser(data.user);
    setTenants(myTenants);

    const first = myTenants[0] ?? null;
    setActiveTenantState(first);
    if (first) {
      localStorage.setItem("active_tenant", first.tenant.slug);
    }

    return first; // This must return the object
  };

  const logout = () => {
    tokenStore.clear();
    setUser(null);
    setTenants([]);
    setActiveTenantState(null);
  };

  const setActiveTenant = (slug: string) => {
    const found = tenants.find((m) => m.tenant.slug === slug);
    if (found) {
      setActiveTenantState(found);
      localStorage.setItem("active_tenant", slug);
    }
  };

  // 3. This will now pass smoothly without red squigglies!
  return (
    <AuthContext.Provider value={{ user, activeTenant, tenants, isLoading, login, logout, setActiveTenant }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function useRequireAuth() {
  const auth = useAuth();
  useEffect(() => {
    if (!auth.isLoading && !auth.user) {
      window.location.href = "/login";
    }
  }, [auth.isLoading, auth.user]);
  return auth;
}
