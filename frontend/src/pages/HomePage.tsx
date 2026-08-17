import { Link } from "react-router-dom";
import { getSessionAccessToken } from "../lib/auth/session";

export function HomePage() {
  const authenticated = Boolean(getSessionAccessToken());

  return (
    <section className="panel hero-panel">
      <p className="eyebrow">GeoPilot AI</p>
      <h1>Evidence-first planning intelligence.</h1>
      <p className="lede">
        Connect project and Site context with planning documents, deterministic GIS analysis,
        policy evidence, satellite intelligence and a bounded AI Planning Officer.
      </p>
      <div className="notice" role="note">
        GeoPilot AI is a planning decision-support system. It does not grant statutory approval.
      </div>
      <div className="hero-actions">
        {authenticated ? <Link className="primary-link" to="/projects">Open Projects</Link> : (
          <>
            <Link className="primary-link" to="/register">Create account</Link>
            <Link to="/login">Sign in</Link>
          </>
        )}
      </div>
    </section>
  );
}