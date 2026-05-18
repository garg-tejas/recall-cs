import { BrowserRouter, Routes, Route } from 'react-router-dom'

import { AuthProvider } from './auth/AuthContext'
import AppShell from './components/layout/AppShell'
import DashboardPage from './routes/DashboardPage'
import LandingPage from './routes/LandingPage'
import ReviewPage from './routes/ReviewPage'
import LearningPathPage from './routes/LearningPathPage'
import ReviewSetupPage from './routes/ReviewSetupPage'
import ReviewSummaryPage from './routes/ReviewSummaryPage'
import TutorPage from './routes/TutorPage'
import LoginPage from './routes/LoginPage'
import SignupPage from './routes/SignupPage'
import ProtectedRoute from './routes/ProtectedRoute'

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell mode="workspace" width="wide" />}>
            <Route path="/" element={<LandingPage />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell mode="workspace" width="content" />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/tutor" element={<TutorPage />} />
              <Route path="/review/setup" element={<ReviewSetupPage />} />
              <Route path="/review/path" element={<LearningPathPage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/review/summary" element={<ReviewSummaryPage />} />
            </Route>
          </Route>
          <Route element={<AppShell mode="auth" width="content" />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
          </Route>
          <Route element={<AppShell mode="plain" width="narrow" />}>
            <Route
              path="*"
              element={
                <div className="layout-stack layout-stack--sm">
                  <h1>404 - Not Found</h1>
                  <p className="u-muted">The requested page does not exist.</p>
                </div>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
