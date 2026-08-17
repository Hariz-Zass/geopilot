import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlanningMapPage } from "../pages/PlanningMapPage";
import { ProjectPage } from "../pages/ProjectPage";
import { ProjectDocumentsPage } from "../pages/ProjectDocumentsPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { RegisterPage } from "../pages/RegisterPage";
import { SystemPage } from "../pages/SystemPage";
import { TrackBWorkspacePage } from "../pages/TrackBWorkspacePage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "register", element: <RegisterPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "projects/:projectId", element: <ProjectPage /> },
      { path: "projects/:projectId/map", element: <PlanningMapPage /> },
      { path: "projects/:projectId/documents", element: <ProjectDocumentsPage /> },
      { path: "projects/:projectId/track-b", element: <TrackBWorkspacePage /> },
      { path: "system", element: <SystemPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);