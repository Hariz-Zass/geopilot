import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { frontendEnv } from "../config/env";
import { clearSessionAccessToken, getSessionAccessToken } from "../lib/auth/session";

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const authenticated = Boolean(getSessionAccessToken());

  function logout() {
    clearSessionAccessToken();
    navigate("/login");
  }

  return (
    <div className={`app-shell ${location.pathname.includes("/track-b") ? "trackb-app" : ""}`}>
      <header className="topbar">
        <div>
          <p className="brand-kicker">Planning decision support</p>
          <strong className="brand">{frontendEnv.appName}</strong>
        </div>
        <nav aria-label="Primary navigation" className="nav-links" data-location={location.pathname}>
          <NavLink to="/" end>Home</NavLink>
          {authenticated ? (
            <>
              <NavLink to="/projects">Projects</NavLink>
              <NavLink to="/system">System</NavLink>
              <button className="nav-button" type="button" onClick={logout}>Sign out</button>
            </>
          ) : (
            <>
              <NavLink to="/login">Sign in</NavLink>
              <NavLink to="/register">Register</NavLink>
              <NavLink to="/system">System</NavLink>
            </>
          )}
        </nav>
      </header>
      <main className={`app-content ${location.pathname.includes("/track-b") ? "trackb-app-content" : ""}`}>
        <Outlet />
      </main>
    </div>
  );
}