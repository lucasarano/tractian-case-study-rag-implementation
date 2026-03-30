import { Navigate, Route, Routes } from "react-router-dom";
import { PageShell } from "./components/layout/PageShell";
import Dashboard from "./pages/Dashboard";
import RagFunctionality from "./pages/Troubleshoot";

export default function App() {
  return (
    <PageShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/rag" element={<RagFunctionality />} />
        <Route path="/ingest/manuals" element={<Navigate to="/rag" replace />} />
        <Route path="/ingest/logs" element={<Navigate to="/rag" replace />} />
        <Route path="/troubleshoot" element={<Navigate to="/rag" replace />} />
        <Route path="/sessions" element={<Navigate to="/rag" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </PageShell>
  );
}
