import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Repositories from "./pages/Repositories";
import RepoDetails from "./pages/RepoDetails";
import Layout from "./components/Layout";
import Alerts from "./pages/Alerts";
import Settings from "./pages/Settings";
import Billing from "./pages/Billing";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route path="/repositories/:id" element={<RepoDetails />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/billing" element={<Billing />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
