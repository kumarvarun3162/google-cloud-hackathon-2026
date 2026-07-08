import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./lib/auth.jsx";
import ProtectedRoute from "./lib/ProtectedRoute.jsx";
import SubmitPage from "./pages/SubmitPage";
import LoginPage from "./pages/LoginPage";
import HotspotMapPage from "./pages/HotspotMapPage";
import PrioritiesPage from "./pages/PrioritiesPage";

// Public: "/" (citizen submission, Phase 1)
// Auth-gated: "/map" (Phase 2, this step), "/priorities" (Phase 3 stub),
// "/compare" arrives in Phase 4 as a modal/drawer on top of "/priorities"
// rather than its own route.
function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<SubmitPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/map"
            element={
              <ProtectedRoute>
                <HotspotMapPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/priorities"
            element={
              <ProtectedRoute>
                <PrioritiesPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
