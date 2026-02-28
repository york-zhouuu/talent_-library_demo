import { Outlet, Link, useLocation } from 'react-router-dom'
import { Users, Upload, Search, Database } from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { path: '/', icon: Search, label: '智能搜索' },
  { path: '/pools', icon: Database, label: '人才库' },
  { path: '/upload', icon: Upload, label: '批量导入' }
]

export default function Layout() {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <Users className="w-8 h-8 text-blue-600" />
              <span className="text-xl font-bold text-gray-900">人才库管理系统</span>
            </div>
            <div className="flex items-center gap-1">
              {navItems.map(({ path, icon: Icon, label }) => (
                <Link
                  key={path}
                  to={path}
                  className={clsx(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                    location.pathname === path
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
