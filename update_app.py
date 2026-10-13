with open('D:/crm/frontend/src/layouts/AppShell.tsx', 'r') as f:
    content = f.read()

# Change 1: NavLink className - change gap, px, py, text size, span width
old1 = '''className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-400 text-signalink font-semibold shadow'
                    : 'text-graphite-100 hover:bg-graphite-600 hover:text-white'
                }`
              }
              <span className="w-5 text-center">{n.icon}</span>'''

new1 = '''className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-400 text-signalink font-semibold shadow'
                    : 'text-graphite-100 hover:bg-graphite-600 hover:text-white'
                }`
              }
              <span className="w-4 text-center">{n.icon}</span>'''

content = content.replace(old1, new1)

# Change 2: Mobile nav div - change px, py, text size
old2 = '''<div className="md:hidden bg-graphite-700 text-white px-4 py-3 flex gap-4 overflow-x-auto text-sm sticky top-0 z-20 items-center">'''
new2 = '''<div className="md:hidden bg-graphite-700 text-white px-3 py-2 flex gap-4 overflow-x-auto text-xs sticky top-0 z-20 items-center">'''
content = content.replace(old2, new2)

# Change 3: Topbar header - change px, h, text sizes
old3 = '''<header className="bg-white border-b border-graphite-200 px-4 sm:px-6 py-3 flex items-center justify-between gap-2 shrink-0 z-10">'''
new3 = '''<header className="bg-white border-b border-graphite-200 px-3 py-2 flex items-center justify-between gap-2 shrink-0 z-10">'''
content = content.replace(old3, new3)

# Change 4: Inside topbar - gap, text sizes, badge sizes
old4 = '''<div className="flex items-center gap-3 min-w-0">
            <img src="/estar-logo.png" alt="E-Star" className="hidden md:block h-12 w-auto max-w-[170px] rounded object-contain" />
            <div className="text-xs sm:text-sm text-graphite-500 truncate">
              {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' })}
            </div>
          </div>
          <div className="flex items-center gap-3 sm:gap-4 shrink-0">
            {role === 'EMPLOYEE' && <span className="text-sm font-semibold text-graphite-700 truncate max-w-[140px] sm:max-w-none">{userName}</span>}
            <Link to="/notifications" className="relative text-xl" title="Notifications">
              🔔
              {unread > 0 && <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-[#E03131] rounded-full" title={`${unread} unread`} />}
            </Link>
          </div>'''

new4 = '''<div className="flex items-center gap-2 min-w-0">
            <img src="/estar-logo.png" alt="E-Star" className="hidden md:block h-10 w-auto max-w-[150px] rounded object-contain" />
            <div className="text-[10px] text-graphite-500 truncate">
              {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' })}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {role === 'EMPLOYEE' && <span className="text-[10px] font-semibold text-graphite-700 truncate max-w-[120px]">{userName}</span>}
            <Link to="/notifications" className="relative text-lg" title="Notifications">
              🔔
              {unread > 0 && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-[#E03131] rounded-full" title={`${unread} unread`} />}
            </Link>
          </div>'''

content = content.replace(old4, new4)

# Change 5: Main content padding
old5 = '''<main className="flex-1 min-w-0 min-h-0 overflow-y-auto overflow-x-hidden p-3 sm:p-4 md:p-6">'''
new5 = '''<main className="flex-1 min-w-0 min-h-0 overflow-y-auto overflow-x-hidden p-2 sm:p-3 md:p-4 lg:p-6">'''
content = content.replace(old5, new5)

with open('D:/crm/frontend/src/layouts/AppShell.tsx', 'w') as f:
    f.write(content)

print("Changes applied successfully")