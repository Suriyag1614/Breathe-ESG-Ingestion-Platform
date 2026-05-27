import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authApi, tokenStore } from "../lib/api";

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: "", last_name: "", email: "", password: "", password_confirm: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== form.password_confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await authApi.register(form);
      tokenStore.set(data.access);
      tokenStore.setRefresh(data.refresh);
      navigate("/dashboard");
    } catch (err: any) {
      const body = err.body;
      if (body?.errors) {
        const msgs = Object.values(body.errors).flat().join(" ");
        setError(msgs);
      } else {
        setError(body?.detail ?? "Registration failed.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <span className="logo-mark">✦</span>
          <span>Breathe ESG</span>
        </div>
        <h2 className="auth-title">Create account</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-field">
              <label>First name</label>
              <input value={form.first_name} onChange={set("first_name")} required />
            </div>
            <div className="form-field">
              <label>Last name</label>
              <input value={form.last_name} onChange={set("last_name")} required />
            </div>
          </div>
          <div className="form-field">
            <label>Email</label>
            <input type="email" value={form.email} onChange={set("email")} required />
          </div>
          <div className="form-field">
            <label>Password</label>
            <input type="password" value={form.password} onChange={set("password")} required minLength={8} />
          </div>
          <div className="form-field">
            <label>Confirm password</label>
            <input type="password" value={form.password_confirm} onChange={set("password_confirm")} required />
          </div>
          {error && <div className="alert alert-error">{error}</div>}
          <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
            {loading ? <span className="spinner-sm" /> : "Create account"}
          </button>
        </form>
        <div className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </div>
    </div>
  );
}
