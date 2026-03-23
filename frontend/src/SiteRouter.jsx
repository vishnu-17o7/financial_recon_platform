import { Suspense, lazy, useEffect, useState } from "react";

const DashboardApp = lazy(() => import("./App"));
const MarketingLanding = lazy(() => import("./components/MarketingLanding"));

const VIEW_LANDING = "landing";
const VIEW_DASHBOARD = "dashboard";
const DASHBOARD_HASH = "#dashboard";
const DARK_MODE_STORAGE_KEY = "darkMode";

function getCurrentView() {
  if (typeof window === "undefined") {
    return VIEW_LANDING;
  }

  const hash = String(window.location.hash || "").toLowerCase();
  const path = String(window.location.pathname || "").toLowerCase();
  const params = new URLSearchParams(window.location.search || "");

  if (hash === DASHBOARD_HASH || path === "/dashboard" || params.get("view") === VIEW_DASHBOARD) {
    return VIEW_DASHBOARD;
  }

  return VIEW_LANDING;
}

export default function SiteRouter() {
  const [view, setView] = useState(() => getCurrentView());
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }

    const saved = localStorage.getItem(DARK_MODE_STORAGE_KEY);
    return saved ? JSON.parse(saved) : false;
  });

  useEffect(() => {
    const syncView = () => setView(getCurrentView());

    window.addEventListener("hashchange", syncView);
    window.addEventListener("popstate", syncView);

    return () => {
      window.removeEventListener("hashchange", syncView);
      window.removeEventListener("popstate", syncView);
    };
  }, []);

  useEffect(() => {
    localStorage.setItem(DARK_MODE_STORAGE_KEY, JSON.stringify(darkMode));
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  const openDashboard = () => {
    if (window.location.hash.toLowerCase() !== DASHBOARD_HASH) {
      window.location.hash = "dashboard";
    }
    setView(VIEW_DASHBOARD);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openLanding = () => {
    const nextUrl = new URL(window.location.href);
    if (nextUrl.pathname.toLowerCase() === "/dashboard") {
      nextUrl.pathname = "/";
    }
    nextUrl.hash = "";
    nextUrl.searchParams.delete("view");
    window.history.pushState({}, "", `${nextUrl.pathname}${nextUrl.search}`);
    setView(VIEW_LANDING);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const loadingFallback = (
    <div className="route-loading" role="status" aria-live="polite">
      Loading workspace...
    </div>
  );

  return (
    <Suspense fallback={loadingFallback}>
      {view === VIEW_DASHBOARD ? (
        <DashboardApp
          darkMode={darkMode}
          onToggleDarkMode={() => setDarkMode((value) => !value)}
          onNavigateHome={openLanding}
        />
      ) : (
        <MarketingLanding
          onGetStarted={openDashboard}
          darkMode={darkMode}
          onToggleDarkMode={() => setDarkMode((value) => !value)}
        />
      )}
    </Suspense>
  );
}
