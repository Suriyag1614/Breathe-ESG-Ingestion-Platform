import { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "⊞" },
  { to: "/ingest", label: "Ingest Data", icon: "↑" },
  { to: "/queue", label: "Review Queue", icon: "✓" },
  { to: "/audit", label: "Audit Trail", icon: "◷" },
  { to: "/sources", label: "Data Sources", icon: "⚙" },
];

interface AppShellProps {
  children: ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const { user, activeTenant, tenants, logout, setActiveTenant } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const initials = user
    ? `${user.first_name?.[0] ?? ""}${user.last_name?.[0] ?? ""}`.toUpperCase()
    : "?";

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-mark">✦</span>
          Breathe ESG
        </div>

        {tenants.length > 1 && (
          <div className="tenant-selector">
            <select
              value={activeTenant?.tenant.slug ?? ""}
              onChange={(e) => setActiveTenant(e.target.value)}
            >
              {tenants.map((m) => (
                <option key={m.tenant.slug} value={m.tenant.slug}>
                  {m.tenant.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {activeTenant && (
          <div style={{ padding: "8px 16px 4px", fontSize: 11, color: "var(--text-muted)" }}>
            {activeTenant.tenant.name}
            <span className="role-badge" style={{ marginLeft: 6 }}>
              {activeTenant.role}
            </span>
          </div>
        )}

        <ul className="nav-list">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `nav-item${isActive ? " active" : ""}`
                }
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="sidebar-footer">
          <div className="user-pill">
            <div className="avatar">{initials}</div>
            <div className="user-info">
              <div className="user-name">{user?.first_name} {user?.last_name}</div>
              <div className="user-email">{user?.email}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout} title="Sign out">
            ⏻
          </button>
        </div>
      </nav>

      <div className="main-content">
        {children}
      </div>
    </div>
  );
}
