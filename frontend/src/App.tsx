import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { useTheme } from "./theme";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Sources from "./pages/Sources";
import Datasets from "./pages/Datasets";
import DatasetDetail from "./pages/DatasetDetail";
import Dashboards from "./pages/Dashboards";
import DashboardView from "./pages/DashboardView";
import Ask from "./pages/Ask";
import WarehousePage from "./pages/Warehouse";
import Pipelines from "./pages/Pipelines";
import InsightsHub from "./pages/InsightsHub";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

function ThemeBoot() {
  useTheme();
  return null;
}

export default function App() {
  return (
    <AuthProvider>
      <ThemeBoot />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected />}>
            <Route path="/" element={<Home />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/datasets" element={<Datasets />} />
            <Route path="/datasets/:id" element={<DatasetDetail />} />
            <Route path="/dashboards" element={<Dashboards />} />
            <Route path="/dashboards/:id" element={<DashboardView />} />
            <Route path="/insights" element={<InsightsHub />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/warehouse" element={<WarehousePage />} />
            <Route path="/pipelines" element={<Pipelines />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
