import { Users, FileText, BellRing, Activity, ArrowUpRight, Sparkles, Clock } from "lucide-react";

const kpis = [
  { label: "Total Personnel", value: "48", delta: "+3 this week", icon: Users, tone: "primary" as const },
  { label: "Documents", value: "312", delta: "+18 today", icon: FileText, tone: "info" as const },
  { label: "Pending Approvals", value: "27", delta: "-5 vs yesterday", icon: BellRing, tone: "warning" as const },
  { label: "System Health", value: "99.9%", delta: "All systems live", icon: Activity, tone: "success" as const },
];

const toneStyles = {
  primary: "bg-primary-soft text-primary",
  info: "bg-info/10 text-info",
  warning: "bg-warning/10 text-warning",
  success: "bg-success/10 text-success",
};

export const HeroBanner = () => {
  const now = new Date().toLocaleString("en-US", {
    weekday: "long", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

  return (
    <section className="anim-fade-up relative overflow-hidden rounded-2xl bg-gradient-hero p-8 lg:p-10 text-primary-foreground shadow-lg">
      {/* Decorative */}
      <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-primary-glow/30 blur-3xl" aria-hidden="true" />
      <div className="absolute bottom-0 left-1/3 h-48 w-48 rounded-full bg-primary-glow/20 blur-3xl" aria-hidden="true" />
      <div
        className="absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, white 1px, transparent 0)",
          backgroundSize: "32px 32px",
        }}
        aria-hidden="true"
      />

      <div className="relative grid gap-8 lg:grid-cols-[1.2fr_1fr] items-center">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-sm border border-white/15 text-xs font-medium tracking-wide">
            <Sparkles className="h-3.5 w-3.5" />
            Admin Command Center
          </div>
          <h1 className="mt-4 text-3xl lg:text-4xl xl:text-5xl font-bold tracking-tight leading-tight">
            Operations Pulse <span className="text-primary-glow/80">&amp;</span> Workflow Control
          </h1>
          <p className="mt-3 text-primary-foreground/75 text-sm lg:text-base max-w-xl">
            Manage users, monitor workflow load, and tune notifications from one streamlined dashboard.
          </p>
          <div className="mt-5 flex items-center gap-2 text-xs text-primary-foreground/70">
            <Clock className="h-3.5 w-3.5" />
            {now}
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-white text-primary font-semibold text-sm shadow-sm hover:bg-white/95 transition">
              Open MMR Hub <ArrowUpRight className="h-4 w-4" />
            </button>
            <button className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-white/10 backdrop-blur-sm border border-white/20 text-primary-foreground font-semibold text-sm hover:bg-white/15 transition">
              Manage Devices
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {kpis.map((k) => {
            const Icon = k.icon;
            return (
              <div
                key={k.label}
                className="rounded-xl bg-white/95 text-foreground p-4 shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5"
              >
                <div className={`inline-grid place-items-center h-9 w-9 rounded-lg ${toneStyles[k.tone]}`}>
                  <Icon className="h-4.5 w-4.5" />
                </div>
                <div className="mt-3 text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  {k.label}
                </div>
                <div className="mt-0.5 text-2xl font-bold tracking-tight">{k.value}</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">{k.delta}</div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
