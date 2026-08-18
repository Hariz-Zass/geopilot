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
            Build better plans
            <br />
            from better evidence.
          </h1>

          <p className="gp-auth-intro">
            Create your GeoPilot workspace and bring
            planning documents, spatial evidence and
            AI-assisted analysis into one environment.
          </p>

          <div className="gp-auth-capabilities">
            <div>
              <span className="gp-auth-capability-number">
                01
              </span>

              <span>
                <strong>Evidence First</strong>
                <small>
                  Ground decisions in traceable sources
                </small>
              </span>
            </div>

            <div>
              <span className="gp-auth-capability-number">
                02
              </span>

              <span>
                <strong>Spatial Context</strong>
                <small>
                  Connect planning questions to geography
                </small>
              </span>
            </div>

            <div>
              <span className="gp-auth-capability-number">
                03
              </span>

              <span>
                <strong>Planning Intelligence</strong>
                <small>
                  Move from information to decision support
                </small>
              </span>
            </div>
          </div>
        </div>

        <div
          className="gp-auth-coordinate"
          aria-hidden="true"
        >
          <span>GEOPILOT / ACCOUNT INITIALIZATION</span>
          <span>PLANNING SYSTEM READY</span>
        </div>
      </div>

      <div className="gp-auth-form-side">
        <div className="gp-auth-form-wrap">
          <div className="gp-auth-mobile-brand">
            <span className="gp-auth-mobile-dot" />
            GeoPilot AI
          </div>

          <p className="gp-auth-form-kicker">
            CREATE YOUR WORKSPACE
          </p>

          <h2>Join GeoPilot</h2>

          <p className="gp-auth-form-copy">
            Create an account to start your planning
            intelligence workspace.
          </p>

          <form
            className="gp-auth-form"
            onSubmit={submit}
          >
            <label>
              <span>Display name</span>

              <input
                value={displayName}
                onChange={(event) =>
                  setDisplayName(event.target.value)
                }
                autoComplete="name"
                placeholder="Your name"
                required
              />
            </label>

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
                minLength={12}
                value={password}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
                autoComplete="new-password"
                placeholder="Minimum 12 characters"
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
                {busy
                  ? "Creating..."
                  : "Create workspace"}
              </span>

              {!busy && (
                <span aria-hidden="true">→</span>
              )}
            </button>
          </form>

          <div className="gp-auth-switch">
            <span>Already registered?</span>

            <Link to="/login">
              Sign in
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
