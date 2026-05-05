import { Search, MoreHorizontal, UserPlus } from "lucide-react";

interface User {
  name: string;
  initials: string;
  role: string;
  email: string;
  status: "active" | "away" | "offline";
  lastActive: string;
  workload: number;
}

const users: User[] = [
  { name: "Sara Al-Hamadi", initials: "SA", role: "Operations Manager", email: "sara.h@injaaz.com", status: "active", lastActive: "2 min ago", workload: 84 },
  { name: "Khalid Rahman", initials: "KR", role: "Supervisor", email: "khalid.r@injaaz.com", status: "active", lastActive: "5 min ago", workload: 67 },
  { name: "Layla Mansour", initials: "LM", role: "Business Development", email: "layla.m@injaaz.com", status: "away", lastActive: "1 hr ago", workload: 42 },
  { name: "Omar Siddiqui", initials: "OS", role: "Procurement", email: "omar.s@injaaz.com", status: "active", lastActive: "just now", workload: 91 },
  { name: "Fatima Nasser", initials: "FN", role: "General Manager", email: "fatima.n@injaaz.com", status: "offline", lastActive: "yesterday", workload: 23 },
  { name: "Yousef Tariq", initials: "YT", role: "Supervisor", email: "yousef.t@injaaz.com", status: "active", lastActive: "12 min ago", workload: 58 },
];

const statusDot = {
  active: "bg-success",
  away: "bg-warning",
  offline: "bg-muted-foreground/40",
};

const statusLabel = {
  active: "Active",
  away: "Away",
  offline: "Offline",
};

export const UsersSection = () => (
  <section
    id="section-users"
    className="rounded-2xl bg-card border border-border shadow-card overflow-hidden anim-fade-up"
    style={{ animationDelay: "120ms" }}
  >
    <header className="flex flex-col gap-3 sm:flex-row sm:items-center justify-between p-5 border-b border-border">
      <div>
        <h2 className="text-base font-bold tracking-tight">Team Management</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Active operators across all departments</p>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative flex-1 sm:flex-none">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            placeholder="Search operators…"
            className="h-9 w-full sm:w-56 pl-8 pr-3 text-sm rounded-lg bg-muted border border-transparent focus:border-primary/30 focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/15 transition"
          />
        </div>
        <select className="h-9 px-3 text-sm rounded-lg bg-muted border border-transparent focus:border-primary/30 focus:bg-background focus:outline-none transition">
          <option>All Roles</option>
          <option>Supervisor</option>
          <option>Ops Manager</option>
          <option>Business Dev</option>
          <option>Procurement</option>
        </select>
        <button className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary-hover transition">
          <UserPlus className="h-4 w-4" /> <span className="hidden sm:inline">Add</span>
        </button>
      </div>
    </header>

    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground bg-muted/40">
            <th className="font-semibold px-5 py-3">Operator</th>
            <th className="font-semibold px-3 py-3">Role</th>
            <th className="font-semibold px-3 py-3">Status</th>
            <th className="font-semibold px-3 py-3">Workload</th>
            <th className="font-semibold px-3 py-3">Last active</th>
            <th className="font-semibold px-5 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {users.map((u) => (
            <tr key={u.email} className="hover:bg-muted/40 transition-colors">
              <td className="px-5 py-3">
                <div className="flex items-center gap-3">
                  <div className="relative h-9 w-9 rounded-full bg-gradient-primary grid place-items-center text-primary-foreground font-semibold text-xs flex-shrink-0">
                    {u.initials}
                    <span className={`absolute -bottom-0 -right-0 h-2.5 w-2.5 rounded-full ${statusDot[u.status]} ring-2 ring-card`} />
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-foreground truncate">{u.name}</div>
                    <div className="text-xs text-muted-foreground truncate">{u.email}</div>
                  </div>
                </div>
              </td>
              <td className="px-3 py-3 text-muted-foreground">{u.role}</td>
              <td className="px-3 py-3">
                <span className="inline-flex items-center gap-1.5 text-xs font-medium">
                  <span className={`h-1.5 w-1.5 rounded-full ${statusDot[u.status]}`} />
                  {statusLabel[u.status]}
                </span>
              </td>
              <td className="px-3 py-3 min-w-[140px]">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-primary transition-all"
                      style={{ width: `${u.workload}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium text-muted-foreground tabular-nums w-9 text-right">
                    {u.workload}%
                  </span>
                </div>
              </td>
              <td className="px-3 py-3 text-xs text-muted-foreground">{u.lastActive}</td>
              <td className="px-5 py-3 text-right">
                <button className="inline-grid place-items-center h-8 w-8 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition">
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>

    <footer className="flex items-center justify-between px-5 py-3 border-t border-border text-xs text-muted-foreground">
      <span>Showing <strong className="text-foreground">6</strong> of <strong className="text-foreground">48</strong> operators</span>
      <div className="flex gap-1">
        <button className="px-2.5 py-1 rounded-md hover:bg-muted">Prev</button>
        <button className="px-2.5 py-1 rounded-md bg-primary text-primary-foreground font-semibold">1</button>
        <button className="px-2.5 py-1 rounded-md hover:bg-muted">2</button>
        <button className="px-2.5 py-1 rounded-md hover:bg-muted">Next</button>
      </div>
    </footer>
  </section>
);
