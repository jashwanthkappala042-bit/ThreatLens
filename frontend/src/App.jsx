import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import ScrollToTop from "./components/ScrollToTop";
import About from "./pages/About";
import AuthPage from "./pages/AuthPage";
import Community from "./pages/Community";
import CommunityPost from "./pages/CommunityPost";
import Complaints from "./pages/Complaints";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import Landing from "./pages/Landing";
import Moderation from "./pages/Moderation";
import NotFound from "./pages/NotFound";
import Profile from "./pages/Profile";
import Results from "./pages/Results";
import Scanner from "./pages/Scanner";

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />

        <Route element={<Layout />}>
          <Route index element={<Landing />} />
          <Route path="scan" element={<Scanner />} />
          <Route path="results/:id" element={<Results />} />
          <Route path="about" element={<About />} />

          <Route path="community" element={<Community />} />
          <Route path="community/:id" element={<CommunityPost />} />

          <Route
            path="dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="history"
            element={
              <ProtectedRoute>
                <History />
              </ProtectedRoute>
            }
          />
          <Route
            path="complaints"
            element={
              <ProtectedRoute>
                <Complaints />
              </ProtectedRoute>
            }
          />
          <Route
            path="profile"
            element={
              <ProtectedRoute>
                <Profile />
              </ProtectedRoute>
            }
          />
          <Route
            path="moderation"
            element={
              <ProtectedRoute admin>
                <Moderation />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </>
  );
}
