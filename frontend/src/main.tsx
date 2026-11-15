import { lazy, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./styles/index.css";
import Layout from "./components/Layout";
import { AppProvider } from "./state/AppContext";
import { AdminProvider } from "./state/AdminContext";
import Overview from "./pages/Overview";
const CheckIn = lazy(() => import("./pages/CheckIn"));
const Trends = lazy(() => import("./pages/Trends"));
const DigitalTwin = lazy(() => import("./pages/DigitalTwin"));
const Agents = lazy(() => import("./pages/Agents"));
const Countermeasures = lazy(() => import("./pages/Countermeasures"));
const Reports = lazy(() => import("./pages/Reports"));
const Settings = lazy(() => import("./pages/Settings"));
const CarePlan = lazy(() => import("./pages/CarePlan"));
const AnalysisResult = lazy(() => import("./pages/AnalysisResult"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider>
      <AdminProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="check-in" element={<CheckIn />} />
            <Route path="trends" element={<Trends />} />
            <Route path="digital-twin" element={<DigitalTwin />} />
            <Route path="agents" element={<Agents />} />
            <Route path="care-plan" element={<CarePlan />} />
            <Route path="analysis/:runId" element={<AnalysisResult />} />
            <Route path="countermeasures" element={<Countermeasures />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Overview />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </AdminProvider>
    </AppProvider>
  </StrictMode>,
);
