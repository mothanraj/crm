import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { api } from '../services/api';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '◧', roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
  { to: '/leads', label: 'Leads', icon: '☰', roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
  { to: '/import', label: 'Import', icon: '⤴', roles: ['ADMIN'] },
  { to: '/employees', label: 'Employees', icon: '👤', roles: ['ADMIN'] },
  { to: '/employee-leads', label: 'Employee Leads', icon: '👥', roles: ['ADMIN'] },
  { to: '/reassignments', label: 'Reassign', icon: '⇄', roles: ['ADMIN'] },
  { to: '/reports', label: 'Reports', icon: '▥', roles: ['ADMIN', 'MANAGER'] },
  { to: '/notifications', label: 'Notifications', icon: '🔔', roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
];

export function AppShell() {
  const navigate = useNavigate();
  const role = localStorage.getItem('role') || 'EMPLOYEE';
  const [unread, setUnread] = useState(0);
  const [userName, setUserName] = useState(localStorage.getItem('user_name') || role);
  useEffect(() => {
    const loadUnread = () => {
      api.get('/notifications').then((r) => {
        const items = Array.isArray(r.data) ? r.data : [];
        setUnread(items.filter((n: any) => !n.is_read).length);
      }).catch(() => {});
    };
    loadUnread();
    const t = setInterval(loadUnread, 60000);
    const onRead = () => setUnread(0);
    window.addEventListener('crm:notifications-read', onRead);
    return () => {
      clearInterval(t);
      window.removeEventListener('crm:notifications-read', onRead);
    };
  }, []);
  useEffect(() => {
    if (localStorage.getItem('user_name')) return;
    api.get('/masters').then(({ data }) => {
      const id = localStorage.getItem('user_id');
      const name = data.employees?.find((employee: any) => employee.id === id)?.name;
      if (name) { localStorage.setItem('user_name', name); setUserName(name); }
    }).catch(() => {});
  }, [role]);
  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('role');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_name');
    navigate('/login', { replace: true });
  };
  return (
    <div className="flex min-h-screen">
      {/* sidebar — graphite gradient, signal active pill */}
      <aside className="w-60 shrink-0 hidden md:flex flex-col text-white bg-gradient-to-b from-graphite-500 via-graphite-700 to-graphite-800">
        <div className="px-5 py-5 flex items-center gap-2.5">
          <img src="/estar-logo.jpg" alt="E-Star" className="w-9 h-9 rounded-lg object-contain bg-white" />
          <div>
            <div className="text-white font-bold leading-tight">E-Star CRM</div>
            <div className="text-[11px] text-graphite-200">Lead Management</div>
          </div>
        </div>
        <nav className="px-3 space-y-1 flex-1">
          {NAV.filter((n) => n.roles.includes(role)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-400 text-signalink font-semibold shadow'
                    : 'text-graphite-100 hover:bg-graphite-600 hover:text-white'
                }`
              }
            >
              <span className="w-5 text-center">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-white/10">
          <div className="text-[11px] text-graphite-200 uppercase tracking-wider mb-1">Signed in as</div>
          <div className="text-sm font-medium text-white">{userName}</div>
          <button onClick={logout} className="mt-3 text-xs text-graphite-200 hover:text-brand-400 underline underline-offset-2">
            Sign out
          </button>
        </div>
      </aside>

      {/* main */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* mobile nav */}
        <div className="md:hidden bg-graphite-700 text-white px-4 py-3 flex gap-4 overflow-x-auto text-sm sticky top-0 z-20 items-center">
          <img src="/estar-logo.jpg" alt="E-Star" className="w-7 h-7 rounded object-contain bg-white shrink-0" />
          {NAV.filter((n) => n.roles.includes(role)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              aria-current={undefined}
              className={({ isActive }) => `whitespace-nowrap ${isActive ? 'text-brand-400 font-semibold' : ''}`}
            >
              {n.label}
            </NavLink>
          ))}
          <button onClick={logout} className="whitespace-nowrap text-graphite-200 underline underline-offset-2">Sign out</button>
        </div>
        {/* topbar */}
        <header className="bg-white border-b border-graphite-200 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <img src="/estar-logo.jpg" alt="E-Star" className="hidden md:block w-8 h-8 rounded object-contain" />
            <div className="text-sm text-graphite-500">
              {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' })}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {role === 'EMPLOYEE' && <span className="text-sm font-semibold text-graphite-700">{userName}</span>}
            <Link to="/notifications" className="relative text-xl" title="Notifications">
              🔔
              {unread > 0 && <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-[#E03131] rounded-full" title={`${unread} unread`} />}
            </Link>
          </div>
        </header>
        <main className="p-6 max-w-[1400px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
