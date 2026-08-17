import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../lib/api/auth";
import { ApiError } from "../lib/api/errors";
import { setSessionAccessToken } from "../lib/auth/session";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const response = await authApi.login({ email, password });
      setSessionAccessToken(response.access_token);
      navigate("/projects");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel auth-panel">
      <p className="eyebrow">Account</p>
      <h1>Sign in to GeoPilot AI</h1>
      <form className="stack-form" onSubmit={submit}>
        <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <div className="status-card status-error" role="alert">{error}</div>}
        <button type="submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
      </form>
      <p>New user? <Link to="/register">Create an account</Link>.</p>
    </section>
  );
}