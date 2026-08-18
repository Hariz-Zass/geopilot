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
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to sign in.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="gp-auth-shell">
      <div className="gp-auth-visual">
        <div className="gp-auth-grid" aria-hidden="true" />

        <div
          className="gp-auth-orbit gp-auth-orbit-one"
          aria-hidden="true"
        />

        <div
          className="gp-auth-orbit gp-auth-orbit-two"
          aria-hidden="true"
        />

        <div className="gp-auth-brand">
          <div
            className="gp-auth-brand-mark"
            aria-hidden="true"
          >
            <span />
            <span />
            <span />
          </div>

          <p className="gp-auth-kicker">
            GEOSPATIAL PLANNING INTELLIGENCE
          </p>

          <h1>
            Plan with evidence.
            <br />
            Decide with intelligence.
          </h1>

          <p className="gp-auth-intro">
            GeoPilot AI brings spatial evidence, planning
            policy and AI-assisted reasoning into one
            decision-support workspace.
          </p>

          <div className="gp-auth-capabilities">
            <div>
              <span className="gp-auth-capability-number">
                01
              </span>

              <span>
                <strong>Spatial Analysis</strong>
                <small>
                  Terrain, GIS and site intelligence
                </small>
              </span>
            </div>

            <div>
              <span className="gp-auth-capability-number">
                02
              </span>

              <span>
                <strong>Planning Policy</strong>
                <small>
                  Evidence-grounded document intelligence
                </small>
              </span>
            </div>

            <div>
              <span className="gp-auth-capability-number">
                03
              </span>

              <span>
                <strong>AI Decision Support</strong>
                <small>
                  Traceable planning assistance
                </small>
              </span>
            </div>
          </div>
        </div>

        <div
          className="gp-auth-coordinate"
          aria-hidden="true"
        >
          <span>GEOPILOT / PLANNING WORKSPACE</span>
          <span>SPATIAL INTELLIGENCE ONLINE</span>
        </div>
      </div>

      <div className="gp-auth-form-side">
        <div className="gp-auth-form-wrap">
          <div className="gp-auth-mobile-brand">
            <span className="gp-auth-mobile-dot" />
            GeoPilot AI
          </div>

          <p className="gp-auth-form-kicker">
            PLANNING INTELLIGENCE WORKSPACE
          </p>

          <h2>Welcome back</h2>

          <p className="gp-auth-form-copy">
            Sign in to continue to your GeoPilot planning
            workspace.
          </p>

          <form
            className="gp-auth-form"
            onSubmit={submit}
          >
            <label>
              <span>Email address</span>

              <input
                type="email"
                value={email}
                onChange={(event) =>
                  setEmail(event.target.value)
                }
                autoComplete="email"
                placeholder="planner@example.com"
                required
              />
            </label>

            <label>
              <span>Password</span>

              <input
                type="password"
                value={password}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
                autoComplete="current-password"
                placeholder="Enter your password"
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

            <button
              className="gp-auth-submit"
              type="submit"
              disabled={busy}
            >
              <span>
                {busy ? "Signing in..." : "Enter GeoPilot"}
              </span>

              {!busy && (
                <span aria-hidden="true">→</span>
              )}
            </button>
          </form>

          <div className="gp-auth-switch">
            <span>New to GeoPilot?</span>

            <Link to="/register">
              Create an account
            </Link>
          </div>

          <p className="gp-auth-footnote">
            Evidence-grounded planning decision support
          </p>
        </div>
      </div>
    </section>
  );
}
