import { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

interface AppShellProps {
  children: ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const { user, activeTenant, tenants, logout, setActiveTenant } = useAuth();
  const navigate = useNavigate();

  // 1. DYNAMIC FALLBACK: If context isn't ready yet, pull the saved slug from localStorage
  const savedSlug = localStorage.getItem("active_tenant");
  const slug = activeTenant?.tenant?.slug || savedSlug || "";

  // 2. Compute navigation links dynamically inside the component render lifecycle
  const NAV_ITEMS = [
    { to: `/tenant/${slug}/dashboard`, label: "Dashboard", icon: "⊞" },
    { to: `/tenant/${slug}/ingest`, label: "Ingest Data", icon: "↑" },
    { to: `/tenant/${slug}/queue`, label: "Review Queue", icon: "✓" },
    { to: `/tenant/${slug}/audit`, label: "Audit Trail", icon: "◷" },
    { to: `/tenant/${slug}/sources`, label: "Data Sources", icon: "⚙" },
  ];

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

        {/* 3. Render items ONLY if we have a valid slug to prevent broken link clicks */}
        <ul className="nav-list">
          {slug ? (
            NAV_ITEMS.map((item) => (
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
            ))
          ) : (
            <div style={{ padding: "16px", color: "var(--text-muted)", fontSize: "12px" }}>
              Loading workspace links...
            </div>
          )}
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