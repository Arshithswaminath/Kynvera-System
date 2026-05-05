import { Activity, FileText, UserPlus, Settings, CheckCircle2 } from "lucide-react";

const events = [
  { icon: CheckCircle2, color: "text-success", bg: "bg-success/10", title: "MMR Report approved", who: "S. Al-Hamadi", when: "2 min ago" },
  { icon: UserPlus, color: "text-info", bg: "bg-info/10", title: "New operator onboarded", who: "Y. Tariq", when: "1 hr ago" },
  { icon: FileText, color: "text-primary", bg: "bg-primary-soft", title: "Inspection #INS-2491 submitted", who: "K. Rahman", when: "3 hr ago" },
  { icon: Settings, color: "text-warning", bg: "bg-warning/10", title: "Chargeable rule updated", who: "F. Nasser", when: "Yesterday" },
  { icon: Activity, color: "text-info", bg: "bg-info/10", title: "Device DEV-018 came back online", who: "System", when: "Yesterday" },
];

export const ActivityFeed = () => (
  <aside className="rounded-2xl bg-card border border-border shadow-card overflow-hidden anim-fade-up" style={{ animationDelay: "200ms" }}>
    <header className="flex items-center justify-between p-5 border-b border-border">
      <div>
        <h2 className="text-base font-bold tracking-tight">Recent Activity</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Live feed across the platform</p>
      </div>
      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-success">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-success/60 animate-ping" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-success" />
        </span>
        Live
      </span>
    </header>
    <ol className="p-2">
      {events.map((e, i) => {
        const Icon = e.icon;
        return (
          <li key={i} className="flex items-start gap-3 p-3 rounded-lg hover:bg-muted/40 transition">
            <div className={`h-8 w-8 rounded-lg ${e.bg} ${e.color} grid place-items-center flex-shrink-0`}>
              <Icon className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-foreground leading-snug">{e.title}</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                <span className="font-medium">{e.who}</span> · {e.when}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  </aside>
);
