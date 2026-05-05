import { Mail, Bell, MessageSquare, Smartphone } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const channels = [
  { name: "Inspection Forms", desc: "Notify when new inspections submitted", icon: Bell, defaults: { email: true, push: true, sms: false } },
  { name: "HR Forms", desc: "Onboarding, leave requests, profile updates", icon: MessageSquare, defaults: { email: true, push: false, sms: false } },
  { name: "MMR Reports", desc: "Monthly maintenance reports & approvals", icon: Mail, defaults: { email: true, push: true, sms: true } },
  { name: "Device Alerts", desc: "Offline devices, sync issues, battery", icon: Smartphone, defaults: { email: false, push: true, sms: false } },
];

const Toggle = ({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) => (
  <button
    onClick={() => onChange(!on)}
    role="switch"
    aria-checked={on}
    aria-label={label}
    className={cn(
      "relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors",
      on ? "bg-primary" : "bg-muted-foreground/25"
    )}
  >
    <span
      className={cn(
        "inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform",
        on ? "translate-x-[18px]" : "translate-x-0.5"
      )}
    />
  </button>
);

export const NotificationsSection = () => {
  const [state, setState] = useState(channels.map(c => c.defaults));

  return (
    <section
      id="section-notifications"
      className="rounded-2xl bg-card border border-border shadow-card overflow-hidden anim-fade-up"
      style={{ animationDelay: "240ms" }}
    >
      <header className="flex items-center justify-between p-5 border-b border-border">
        <div>
          <h2 className="text-base font-bold tracking-tight">Notification Automation</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Configure delivery channels per workflow</p>
        </div>
        <span className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground hidden sm:inline">
          Email · Push · SMS
        </span>
      </header>

      <div className="divide-y divide-border">
        {channels.map((c, i) => {
          const Icon = c.icon;
          return (
            <div key={c.name} className="flex items-center gap-4 px-5 py-4">
              <div className="h-10 w-10 rounded-lg bg-primary-soft text-primary grid place-items-center flex-shrink-0">
                <Icon className="h-5 w-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm text-foreground">{c.name}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{c.desc}</div>
              </div>
              <div className="flex items-center gap-5">
                {(["email", "push", "sms"] as const).map((k) => (
                  <div key={k} className="flex flex-col items-center gap-1">
                    <Toggle
                      on={state[i][k]}
                      onChange={(v) => {
                        const next = state.map(s => ({ ...s }));
                        next[i][k] = v;
                        setState(next);
                      }}
                      label={`${c.name} ${k}`}
                    />
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold sm:hidden">
                      {k}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
