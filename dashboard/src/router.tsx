import { createBrowserRouter } from "react-router-dom";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { DashboardHome } from "@/pages/DashboardHome";
import { DevicesPage } from "@/pages/DevicesPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { IncidentsPage } from "@/pages/IncidentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { NetworkPage } from "@/pages/NetworkPage";
import { SecurityOperationsPage } from "@/pages/SecurityOperationsPage";
import { SettingsPage } from "@/pages/SettingsPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <DashboardLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <DashboardHome /> },
      { path: "operations", element: <SecurityOperationsPage /> },
      { path: "incidents", element: <IncidentsPage /> },
      { path: "incidents/:incidentId", element: <IncidentDetailPage /> },
      { path: "devices", element: <DevicesPage /> },
      { path: "network", element: <NetworkPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);
