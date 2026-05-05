import { BarChart3, Settings2, Smartphone, Briefcase, ArrowUpRight } from "lucide-react";

const actions = [
  { title: "MMR Dashboard", sub: "Reports, schedule, and generation controls", icon: BarChart3 },
  { title: "Chargeable Rules", sub: "Configure billable units and logic", icon: Settings2 },
  { title: "Device Management", sub: "Track and maintain registered devices", icon: Smartphone },
  { title: "Business Development", sub: "Open BD module and communication tools", icon: Briefcase },
];

export const QuickActions = () => (
  <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 anim-fade-up" style={{ animationDelay: "60ms" }}>
    {actions.map((a) => {
      const Icon = a.icon;
      return (
        <button
          key={a.title}
          className="group text-left p-4 rounded-xl bg-card border border-border hover:border-primary/30 hover:shadow-glow transition-all"
        >
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-lg bg-primary-soft text-primary grid place-items-center group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
              <Icon className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-sm text-foreground">{a.title}</div>
                <ArrowUpRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:-translate-y-0.5 group-hover:translate-x-0.5 transition-transform" />
              </div>
              <div className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{a.sub}</div>
            </div>
          </div>
        </button>
      );
    })}
  </section>
);
