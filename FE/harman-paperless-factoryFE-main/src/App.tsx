import "./App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Provider } from "react-redux";
import { ToastContainer } from "react-toastify";
import MainLayout from "./layout/MainLayout";
import RequireAuth, { RequireAdmin } from "./layout/RequireAuth";
import { ChangeRequestRedirect, NewRecordRedirect, TrackRedirect } from "./layout/LegacyLinks";
import NotFound from "./layout/NotFound";
import LoginPage from "./login";
import { PageLoader } from "./base/feedback";
import store from "./redux/store";

// Each screen is its own chunk: the form designer, charts and grids load only
// where they are used.
const MainDashboard = lazy(() => import("./dashboard"));
const ResourceDashboad = lazy(() => import("./resources/ResourceDashboad"));
const MyFormsDash = lazy(() => import("./myForms/MyFormsDash"));
const FormDetailPage = lazy(() => import("./myForms/FormDetails"));
const ApprovalSetupPage = lazy(() => import("./myForms/ApprovalSetupPage"));
const BuilderDash = lazy(() => import("./templateBuilder"));
const BuilderTemplateDetail = lazy(() => import("./templateBuilder/BuilderTemplateDetail"));
const BuildTemplate = lazy(() => import("./templateBuilder/designer"));
const TemplateRepo = lazy(() => import("./templateRepo"));
const MyApprovalsDash = lazy(() => import("./myApprovals"));
const ApprovalReviewPage = lazy(() => import("./myApprovals/ApprovalReview"));
const PeopleTeamsPage = lazy(() => import("./peopleAndTeams"));
const ChangeRequestDash = lazy(() => import("./changeRequest"));
const ChangeRequestDetailPage = lazy(() => import("./changeRequest/ChnageRequestDetails"));
const ActivityLog = lazy(() => import("./activityLog"));
const DocRepository = lazy(() => import("./docRepository"));
const NotificationsPage = lazy(() => import("./header/NotificationsPage"));
const SettingsPage = lazy(() => import("./header/Settings"));

function App() {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route element={<RequireAuth />}>
              <Route element={<MainLayout />}>
                <Route path="/" element={<MainDashboard />} />
                <Route path="/notifications" element={<NotificationsPage />} />
                <Route path="/settings" element={<SettingsPage />} />

                <Route path="/resources" element={<ResourceDashboad />} />
                <Route path="/doc-repo" element={<DocRepository />} />
                <Route path="/my-forms" element={<MyFormsDash />} />
                <Route path="/my-forms/:id" element={<FormDetailPage />} />
                <Route path="/my-forms/:id/approval" element={<ApprovalSetupPage />} />

                <Route path="/my-approvals" element={<MyApprovalsDash />} />
                <Route path="/my-approvals/:id" element={<ApprovalReviewPage />} />
                <Route path="/request" element={<ChangeRequestDash />} />
                <Route path="/change-request" element={<Navigate to="/request" replace />} />
                <Route path="/change-request/:id" element={<ChangeRequestDetailPage />} />
                <Route path="/change-request/:kind/:id" element={<ChangeRequestDetailPage />} />
                <Route path="/activity-log" element={<ActivityLog />} />
                {/* links written into emails and notifications by the backend */}
                <Route path="/track" element={<TrackRedirect />} />
                <Route path="/records/new" element={<NewRecordRedirect />} />
                <Route path="/change-requests" element={<ChangeRequestRedirect />} />
                {/* reviewers who are not admins open the draft they are asked to approve */}
                <Route path="/builder/:id" element={<BuilderTemplateDetail />} />

                {/* template authoring and people management are admin-only in the API */}
                <Route element={<RequireAdmin />}>
                  <Route path="/builder" element={<BuilderDash />} />
                  <Route path="/builder/:id/build" element={<BuildTemplate />} />
                  <Route path="/builder-repo" element={<TemplateRepo />} />
                  <Route path="/people-teams" element={<PeopleTeamsPage />} />
                </Route>
                <Route path="*" element={<NotFound />} />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
      <ToastContainer position="top-right" autoClose={3000} />
    </Provider>
  );
}

export default App;
