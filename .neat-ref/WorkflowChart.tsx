import { TrendingUp, TrendingDown } from "lucide-react";

const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const submissions = [42, 68, 51, 84, 73, 92, 61];
const approvals = [38, 60, 47, 78, 70, 85, 58];
const max = Math.max(...submissions, ...approvals);

export const WorkflowChart = () => (
  <section className="rounded-2xl bg-card border border-border shadow-card p-5 anim-fade-up" style={{ animationDelay: "260ms" }}>
    <header className="flex items-start justify-between mb-5">
      <div>
        <h2 className="text-base font-bold tracking-tight">Workflow Load</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Submissions vs approvals · last 7 days</p>
      </div>
      <div className="text-right">
        <div className="text-2xl font-bold tracking-tight">471</div>
        <div className="inline-flex items-center gap-1 text-[11px] font-semibold text-success">
          <TrendingUp className="h-3 w-3" /> +12.4%
        </div>
      </div>
    </header>

    <div className="flex items-end justify-between gap-2 h-40">
      {days.map((d, i) => (
        <div key={d} className="flex-1 flex flex-col items-center gap-1.5 group">
          <div className="w-full flex items-end justify-center gap-1 h-32">
            <div
              className="w-3 rounded-t-md bg-gradient-primary transition-all group-hover:opacity-80"
              style={{ height: `${(submissions[i] / max) * 100}%` }}
              title={`Submitted: ${submissions[i]}`}
            />
            <div
              className="w-3 rounded-t-md bg-primary-soft transition-all group-hover:opacity-80"
              style={{ height: `${(approvals[i] / max) * 100}%` }}
              title={`Approved: ${approvals[i]}`}
            />
          </div>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{d}</span>
        </div>
      ))}
    </div>

    <footer className="flex items-center justify-center gap-5 mt-4 pt-4 border-t border-border text-xs">
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm bg-gradient-primary" />
        <span className="text-muted-foreground">Submitted</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm bg-primary-soft" />
        <span className="text-muted-foreground">Approved</span>
      </div>
    </footer>
  </section>
);
