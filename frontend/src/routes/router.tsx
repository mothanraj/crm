import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AppShell } from '../layouts/AppShell';
import { Dashboard, EmployeesPage, ImportPage, LeadDetail, Leads, Login, NotificationsPage, Reports } from '../pages';

function Role({ children, roles }: { children: JSX.Element; roles?: string[] }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" />;
  const r = localStorage.getItem('role') || 'EMPLOYEE';
  if (roles && !roles.includes(r)) return <Navigate to="/dashboard" />;
  return children;
}
function Detail() {
  const { id } = useParams();
  return <LeadDetail id={id!} />;
}
export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<Role roles={['ADMIN', 'MANAGER', 'EMPLOYEE']}><Dashboard /></Role>} />
          <Route path="/leads" element={<Role><Leads /></Role>} />
          <Route path="/leads/:id" element={<Role><Detail /></Role>} />
          <Route path="/import" element={<Role roles={['ADMIN']}><ImportPage /></Role>} />
          <Route path="/employees" element={<Role roles={['ADMIN']}><EmployeesPage /></Role>} />
          <Route path="/reports" element={<Role roles={['ADMIN', 'MANAGER']}><Reports /></Role>} />
          <Route path="/notifications" element={<Role><NotificationsPage /></Role>} />
          <Route path="/" element={<Navigate to="/dashboard" />} />
          <Route path="*" element={<Navigate to="/dashboard" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
