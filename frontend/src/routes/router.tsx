import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AppShell } from '../layouts/AppShell';
import { Dashboard, EmployeeLeads, EmployeesPage, ImportPage, LeadDetail, Leads, Login, NotificationsPage, Reports } from '../pages';

function Role({ children, roles }: { children: React.ReactElement; roles?: string[] }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  const r = localStorage.getItem('role') || 'EMPLOYEE';
  if (roles && !roles.includes(r)) return <Navigate to="/dashboard" replace />;
  return children;
}
function Detail() {
  const { id } = useParams();
  if (!id) return <Navigate to="/leads" replace />;
  return <LeadDetail id={id} />;
}
function LoginGate() {
  const token = localStorage.getItem('token');
  if (token) return <Navigate to="/dashboard" replace />;
  return <Login />;
}
export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginGate />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<Role roles={['ADMIN', 'MANAGER', 'EMPLOYEE']}><Dashboard /></Role>} />
          <Route path="/leads" element={<Role><Leads /></Role>} />
          <Route path="/leads/:id" element={<Role><Detail /></Role>} />
          <Route path="/import" element={<Role roles={['ADMIN']}><ImportPage /></Role>} />
          <Route path="/employees" element={<Role roles={['ADMIN']}><EmployeesPage /></Role>} />
          <Route path="/employee-leads" element={<Role roles={['ADMIN']}><EmployeeLeads /></Role>} />
          <Route path="/reports" element={<Role roles={['ADMIN', 'MANAGER']}><Reports /></Role>} />
          <Route path="/notifications" element={<Role><NotificationsPage /></Role>} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
