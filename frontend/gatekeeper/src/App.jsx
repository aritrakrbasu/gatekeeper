import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, ProtectedRoute } from "./contexts/AuthContext";
import { queryClient } from "./services/queryClient";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import SentryCallback from "./pages/SentryCallback";
import Dashboard from "./pages/Dashboard";
import Repositories from "./pages/Repositories";
import RepoDetails from "./pages/RepoDetails";
import Layout from "./components/Layout";

import Settings from "./pages/Settings";
import Billing from "./pages/Billing";
import Signals from "./pages/Signals";
import Onboarding from "./components/Onboarding";
import GatekeeperLanding from "./pages/GatekeeperLanding";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/" element={<GatekeeperLanding />} />
            <Route path="/login" element={<Login />} />

            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/auth/sentry/callback" element={<SentryCallback />} />
            <Route path="/onboarding" element={<Onboarding />} />
            <Route element={<Layout />}>
              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/repositories"
                element={
                  <ProtectedRoute>
                    <Repositories />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/repositories/:id"
                element={
                  <ProtectedRoute>
                    <RepoDetails />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/signals"
                element={
                  <ProtectedRoute>
                    <Signals />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/settings"
                element={
                  <ProtectedRoute>
                    <Settings />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/billing"
                element={
                  <ProtectedRoute>
                    <Billing />
                  </ProtectedRoute>
                }
              />
            </Route>
          </Routes>
        </Router>
        <ToastContainer
          position="top-right"
          autoClose={5000}
          hideProgressBar={false}
          newestOnTop={false}
          closeOnClick
          rtl={false}
          pauseOnFocusLoss
          draggable
          pauseOnHover
          theme="light"
        />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
