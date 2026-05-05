import { useState } from "react";
import {
  LayoutDashboard, Users, FileText, Bell, BarChart3, Settings2,
  Smartphone, Briefcase, TrendingUp, FolderKanban, Home,
  Search, ChevronsLeft, Menu,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string | number;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const groups: NavGroup[] = [
  {
    label: "Command",
    items: [
      { id: "overview", label: "Dashboard", icon: LayoutDashboard },
      { id: "users", label: "Users", icon: Users, badge: 48 },
      { id: "documents", label: "Documents", icon: FileText, badge: 312 },
      { id: "notifications", label: "Notifications", icon: Bell },
    ],
  },
  {
    label: "Automation",
    items: [
      { id: "reports", label: "Report Generation", icon: BarChart3 },
      { id: "rules", label: "Chargeable Rules", icon: Settings2 },
    ],
  },
  {
    label: "Operations",
    items: [
      { id: "devices", label: "Devices", icon: Smartphone },
      { id: "bd", label: "Business Dev", icon: Briefcase },
      { id: "progress", label: "Personal Progress", icon: TrendingUp },
    ],
  },
  {
    label: "Platform",
    items: [
      { id: "dochub", label: "DocHub", icon: FolderKanban },
      { id: "home", label: "App Home", icon: Home },
    ],
  },
];

interface AdminSidebarProps {
  active: string;
  onSelect: (id: string) => void;
  open: boolean;
  onClose: () => void;
}

export const AdminSidebar = ({ active, onSelect, open, onClose }: AdminSidebarProps) => {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-foreground/40 backdrop-blur-sm lg:hidden transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={cn(
          "fixed lg:sticky top-0 z-50 h-screen flex-shrink-0 border-r border-sidebar-border bg-sidebar transition-all duration-300",
          collapsed ? "w-[78px]" : "w-[272px]",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
        aria-label="Administration menu"
      >
        <div className="flex h-full flex-col">
          {/* Brand */}
          <div className="flex items-center gap-3 px-5 py-5 border-b border-sidebar-border">
            <div className="relative h-10 w-10 flex-shrink-0 rounded-xl bg-gradient-primary grid place-items-center shadow-glow">
              <span className="text-primary-foreground font-bold text-lg">i</span>
              <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-success ring-2 ring-sidebar" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="font-bold text-sidebar-foreground tracking-tight">Injaaz</div>
                <div className="text-[11px] uppercase tracking-wider text-sidebar-muted font-medium">Control Center</div>
              </div>
            )}
            <button
              onClick={() => setCollapsed(c => !c)}
              className="ml-auto hidden lg:grid h-7 w-7 place-items-center rounded-md text-sidebar-muted hover:bg-muted hover:text-sidebar-foreground transition"
              aria-label="Toggle sidebar"
            >
              <ChevronsLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
            </button>
          </div>

          {/* Search */}
          {!collapsed && (
            <div className="px-4 pt-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-sidebar-muted" />
                <input
                  type="text"
                  placeholder="Search…"
                  className="w-full h-9 pl-9 pr-3 text-sm rounded-lg bg-muted border border-transparent focus:border-primary/30 focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/15 transition placeholder:text-sidebar-muted"
                />
                <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-medium text-sidebar-muted bg-background border border-border rounded px-1.5 py-0.5">⌘K</kbd>
              </div>
            </div>
          )}

          {/* Nav */}
          <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-4 space-y-5">
            {groups.map((group) => (
              <div key={group.label}>
                {!collapsed && (
                  <div className="px-3 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-sidebar-muted">
                    {group.label}
                  </div>
                )}
                <div className="space-y-0.5">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = active === item.id;
                    return (
                      <button
                        key={item.id}
                        onClick={() => { onSelect(item.id); onClose(); }}
                        title={collapsed ? item.label : undefined}
                        className={cn(
                          "group relative w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all",
                          isActive
                            ? "bg-sidebar-active-bg text-sidebar-active-fg shadow-xs"
                            : "text-sidebar-foreground hover:bg-muted hover:text-foreground"
                        )}
                      >
                        {isActive && (
                          <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-primary" />
                        )}
                        <Icon className={cn("h-[18px] w-[18px] flex-shrink-0", isActive && "text-primary")} />
                        {!collapsed && (
                          <>
                            <span className="truncate">{item.label}</span>
                            {item.badge !== undefined && (
                              <span className={cn(
                                "ml-auto text-[10.5px] font-semibold px-1.5 py-0.5 rounded-md",
                                isActive
                                  ? "bg-primary text-primary-foreground"
                                  : "bg-muted text-muted-foreground group-hover:bg-background"
                              )}>
                                {item.badge}
                              </span>
                            )}
                          </>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Footer user */}
          <div className="border-t border-sidebar-border p-3">
            <button className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-muted transition group">
              <div className="h-9 w-9 rounded-full bg-gradient-primary grid place-items-center text-primary-foreground font-semibold text-sm flex-shrink-0">
                AM
              </div>
              {!collapsed && (
                <div className="min-w-0 flex-1 text-left">
                  <div className="text-sm font-semibold text-sidebar-foreground truncate">Ahmed Malik</div>
                  <div className="text-[11px] text-sidebar-muted truncate">Operations Manager</div>
                </div>
              )}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
};

export const MobileMenuButton = ({ onClick }: { onClick: () => void }) => (
  <button
    onClick={onClick}
    className="lg:hidden grid h-10 w-10 place-items-center rounded-lg border border-border bg-background hover:bg-muted transition"
    aria-label="Open menu"
  >
    <Menu className="h-5 w-5" />
  </button>
);
