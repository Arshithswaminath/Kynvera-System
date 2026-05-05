import { FileText, FileSpreadsheet, FileCheck2, FileClock, Filter, Download } from "lucide-react";

const docs = [
  { title: "Monthly Maintenance Report — March", type: "MMR", icon: FileSpreadsheet, status: "Approved", color: "success", date: "Mar 31, 2026", owner: "S. Al-Hamadi" },
  { title: "Inspection Form #INS-2491", type: "Inspection", icon: FileCheck2, status: "Pending", color: "warning", date: "Apr 21, 2026", owner: "K. Rahman" },
  { title: "HR Onboarding — Yousef Tariq", type: "HR", icon: FileText, status: "Draft", color: "muted", date: "Apr 18, 2026", owner: "F. Nasser" },
  { title: "Procurement Order #PO-7732", type: "Procurement", icon: FileText, status: "Approved", color: "success", date: "Apr 15, 2026", owner: "O. Siddiqui" },
  { title: "Site Audit — Building C", type: "Audit", icon: FileClock, status: "Review", color: "info", date: "Apr 12, 2026", owner: "L. Mansour" },
];

const statusStyles: Record<string, string> = {
  success: "bg-success/10 text-success border-success/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  info: "bg-info/10 text-info border-info/20",
  muted: "bg-muted text-muted-foreground border-border",
};

export const DocumentsSection = () => (
  <section
    id="section-documents"
    className="rounded-2xl bg-card border border-border shadow-card overflow-hidden anim-fade-up"
    style={{ animationDelay: "180ms" }}
  >
    <header className="flex items-center justify-between p-5 border-b border-border">
      <div>
        <h2 className="text-base font-bold tracking-tight">Document Workflow</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Recent submissions across departments</p>
      </div>
      <div className="flex items-center gap-2">
        <button className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg bg-muted text-foreground text-sm font-medium hover:bg-muted/70 transition">
          <Filter className="h-4 w-4" /> Filter
        </button>
        <button className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg bg-muted text-foreground text-sm font-medium hover:bg-muted/70 transition">
          <Download className="h-4 w-4" /> Export
        </button>
      </div>
    </header>

    <ul className="divide-y divide-border">
      {docs.map((d) => {
        const Icon = d.icon;
        return (
          <li key={d.title} className="flex items-center gap-4 px-5 py-3.5 hover:bg-muted/40 transition cursor-pointer group">
            <div className="h-10 w-10 rounded-lg bg-primary-soft text-primary grid place-items-center flex-shrink-0">
              <Icon className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm text-foreground truncate group-hover:text-primary transition-colors">
                {d.title}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                <span className="font-medium">{d.type}</span>
                <span className="text-border">•</span>
                <span>{d.owner}</span>
                <span className="text-border">•</span>
                <span>{d.date}</span>
              </div>
            </div>
            <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border ${statusStyles[d.color]}`}>
              {d.status}
            </span>
          </li>
        );
      })}
    </ul>
  </section>
);
