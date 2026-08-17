import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { authApi } from "../lib/api/auth";
import { ApiError } from "../lib/api/errors";

export function RegisterPage() {
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);

    try {
      await authApi.register({
        email,
        display_name: displayName,
        password,
      });

      navigate("/login");
    } catch (caught) {
      console.error("REGISTER ERROR:", caught);

      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to create account.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel auth-panel">
      <p className="eyebrow">Account</p>

      <h1>Create your GeoPilot account</h1>

      <form className="stack-form" onSubmit={submit}>
        <label>
          Display name
          <input
            value={displayName}
            onChange={(event) =>
              setDisplayName(event.target.value)
            }
            required
          />
        </label>

        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) =>
              setEmail(event.target.value)
            }
            required
          />
        </label>

        <label>
          Password (minimum 12 characters)
          <input
            type="password"
            minLength={12}
            value={password}
            onChange={(event) =>
              setPassword(event.target.value)
            }
            required
          />
        </label>

        {error && (
          <div
            className="status-card status-error"
            role="alert"
          >
            {error}
          </div>
        )}

        <button type="submit" disabled={busy}>
          {busy ? "Creating..." : "Create account"}
        </button>
      </form>

      <p>
        Already registered? <Link to="/login">Sign in</Link>.
      </p>
    </section>
  );
}