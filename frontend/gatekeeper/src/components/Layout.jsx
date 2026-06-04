import { Outlet, NavLink } from "react-router-dom";
import { useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useWebSocketNotifications } from "../contexts/WebSocketNotificationsContext";
import { useRepositories } from "../services/queries";
import { toast } from "react-toastify";

const Layout = () => {
  const { user, logout } = useAuth();
  const { listenToRepository, stopListeningToRepository } =
    useWebSocketNotifications();
  const { data: repositories = [] } = useRepositories();

  // Automatically listen to all repositories globally
  useEffect(() => {
    if (!repositories || repositories.length === 0) return;

    console.log(
      "[Layout-Global-Notifications] Setting up listeners for all repositories:",
      repositories.length,
    );

    // Listen to all repositories
    repositories.forEach((repo) => {
      if (repo?.id) {
        listenToRepository(repo.id);
      }
    });

    // Cleanup: stop listening when component unmounts
    return () => {
      console.log(
        "[Layout-Global-Notifications] Cleaning up listeners for all repositories",
      );
      repositories.forEach((repo) => {
        if (repo?.id) {
          stopListeningToRepository(repo.id);
        }
      });
    };
  }, [repositories, listenToRepository, stopListeningToRepository]);

  const navLinkClass = ({ isActive }) =>
    `flex items-center gap-3 px-4 py-3 font-medium rounded-2xl transition-all ${
      isActive
        ? "bg-white/80 text-slate-900 shadow-sm border border-white"
        : "text-slate-500 hover:bg-white/60 hover:text-slate-900"
    }`;

  const mobileNavLinkClass = ({ isActive }) =>
    `flex flex-col items-center gap-1 transition-colors ${
      isActive ? "text-[#FC6D26]" : "text-slate-400 hover:text-slate-900"
    }`;

  const mobileIconClass = ({ isActive }) =>
    `p-2 rounded-full transition-all ${isActive ? "bg-[#FC6D26]/10" : ""}`;

  // Get user avatar URL or use dicebear fallback
  const userAvatar =
    user?.avatar_url ||
    `https://api.dicebear.com/7.x/notionists/svg?seed=${user?.username || "User"}`;
  const userName = user?.name || user?.username || "User";

  const handleLogout = () => {
    logout();
  };

  return (
    <div className="relative h-screen bg-[#F2F4F7] font-sans text-slate-900 overflow-hidden selection:bg-[#FC6D26] selection:text-white">
      {/* Ambient Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[40rem] h-[40rem] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40rem] h-[40rem] bg-[#FC6D26]/5 rounded-full blur-[120px] pointer-events-none"></div>

      {/* =========================================
          DESKTOP: FLOATING LEFT SIDEBAR
          ========================================= */}
      <aside className="hidden md:flex flex-col w-64 fixed left-6 top-6 bottom-6 bg-white/60 backdrop-blur-2xl border border-white/80 rounded-[2rem] shadow-[0_8px_32px_rgba(0,0,0,0.04)] z-50">
        {/* Logo Area */}
        <div className="p-8 pb-4 flex items-center gap-3">
          <div className="w-10 h-10 bg-slate-900 text-white rounded-xl flex items-center justify-center font-bold text-lg shadow-md">
            G
          </div>
          <span className="font-semibold text-xl tracking-tight">
            Gatekeeper
          </span>
        </div>

        {/* Desktop Navigation */}
        <nav className="flex-1 px-5 space-y-2 mt-4 overflow-y-auto">
          <NavLink to="/dashboard" className={navLinkClass}>
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
              />
            </svg>
            Dashboard
          </NavLink>
          <NavLink to="/repositories" className={navLinkClass}>
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
              />
            </svg>
            Repositories
          </NavLink>
          <NavLink to="/alerts" className={navLinkClass}>
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"
              />
            </svg>
            Alerts
          </NavLink>
          <NavLink to="/settings" className={navLinkClass}>
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            Settings
          </NavLink>
          <NavLink to="/billing" className={navLinkClass}>
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
              />
            </svg>
            Billing
          </NavLink>
        </nav>

        {/* User Profile */}
        <div className="p-5 mt-auto">
          <div
            className="flex items-center gap-3 p-3 bg-white/40 border border-white/60 rounded-2xl hover:bg-white/60 cursor-pointer transition-all shadow-sm group"
            onClick={handleLogout}
            title="Click to logout"
          >
            <div className="w-10 h-10 rounded-xl bg-slate-200 overflow-hidden shrink-0">
              <img
                src={userAvatar}
                alt={userName}
                className="w-full h-full object-cover"
              />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-900 truncate">
                {userName}
              </p>
              <p className="text-xs text-slate-500 truncate group-hover:text-red-500 transition-colors">
                Click to logout
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* =========================================
          MOBILE: FLOATING TOP NAV PILL
          ========================================= */}
      <header className="md:hidden fixed top-4 left-4 right-4 bg-white/70 backdrop-blur-2xl border border-white/80 rounded-full shadow-[0_8px_32px_rgba(0,0,0,0.04)] z-50 flex items-center justify-between px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-slate-900 text-white rounded-full flex items-center justify-center font-bold text-sm shadow-md">
            G
          </div>
          <span className="font-semibold text-lg tracking-tight">
            Gatekeeper
          </span>
        </div>
        <div
          className="w-8 h-8 rounded-full bg-slate-200 border-2 border-white shadow-sm overflow-hidden"
          onClick={handleLogout}
          title="Click to logout"
        >
          <img
            src={userAvatar}
            alt={userName}
            className="w-full h-full object-cover"
          />
        </div>
      </header>

      {/* =========================================
          MAIN CONTENT AREA (Outlet renders here)
          ========================================= */}
      <main className="h-full h-min-screen   overflow-y-auto overflow-x-hidden md:pl-[19rem] w-full pt-24 md:pt-6 pb-28 md:pb-6 relative z-10">
        <Outlet />
      </main>

      {/* =========================================
          MOBILE: FLOATING BOTTOM NAV PILL
          ========================================= */}
      <nav className="md:hidden fixed bottom-6 left-4 right-4 bg-white/70 backdrop-blur-2xl border border-white/80 rounded-full shadow-[0_8px_32px_rgba(0,0,0,0.06)] z-50">
        <div className="flex items-center justify-around px-2 py-3">
          <NavLink to="/dashboard" className={mobileNavLinkClass}>
            <div className={mobileIconClass}>
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
                />
              </svg>
            </div>
          </NavLink>
          <NavLink to="/repositories" className={mobileNavLinkClass}>
            <div className={mobileIconClass}>
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                />
              </svg>
            </div>
          </NavLink>
          <NavLink to="/alerts" className={mobileNavLinkClass}>
            <div className={mobileIconClass}>
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"
                />
              </svg>
            </div>
          </NavLink>
          <NavLink to="/settings" className={mobileNavLinkClass}>
            <div className={mobileIconClass}>
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
              </svg>
            </div>
          </NavLink>
          <NavLink to="/billing" className={mobileNavLinkClass}>
            <div className={mobileIconClass}>
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
                />
              </svg>
            </div>
          </NavLink>
        </div>
      </nav>
    </div>
  );
};

export default Layout;
