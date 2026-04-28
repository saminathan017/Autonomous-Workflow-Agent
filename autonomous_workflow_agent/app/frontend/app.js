import React, { useCallback, useEffect, useMemo, useState } from "https://esm.sh/react@18";
import { createRoot } from "https://esm.sh/react-dom@18/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);
const API = "/api";

const DEMO_SUMMARY = {
  total_emails: 148,
  success_rate: 96.2,
  successful_runs: 24,
  active_actions: 17,
  total_drafts: 12,
  category_distribution: {
    CUSTOMER_INQUIRY: 42,
    GENERAL: 31,
    URGENT: 22,
    INVOICE: 18,
    NEWSLETTER: 24,
    SPAM: 11,
  },
  sentiment_distribution: {
    POSITIVE: 54,
    NEUTRAL: 67,
    NEGATIVE: 27,
  },
};

const DEMO_RUNS = [
  { run_id: "b58a2a80-1d1a", started_at: "2026-04-27T17:20:00Z", status: "COMPLETED", emails_processed: 18 },
  { run_id: "8a8cd713-09f2", started_at: "2026-04-27T13:10:00Z", status: "COMPLETED", emails_processed: 24 },
  { run_id: "701f95d3-6e6d", started_at: "2026-04-26T19:05:00Z", status: "RUNNING", emails_processed: 9 },
  { run_id: "a2371bc8-3c98", started_at: "2026-04-26T08:45:00Z", status: "COMPLETED", emails_processed: 21 },
];

const DEMO_PRIORITY = {
  emails: [
    {
      email_id: "pri-1",
      subject: "Contract redlines needed before tomorrow’s board packet",
      sender: "Alicia Grant <alicia@northpeak.com>",
      urgency_label: "Important",
      category: "URGENT",
      sentiment: "NEUTRAL",
      processed_at: "2026-04-27T16:40:00Z",
      body_preview: "Please review the revised terms and return your notes by 9 AM so legal can finalize the packet before circulation.",
    },
    {
      email_id: "pri-2",
      subject: "Customer escalation on delayed onboarding timeline",
      sender: "Rahul Menon <rahul@customerhq.io>",
      urgency_label: "Needed Review",
      category: "CUSTOMER_INQUIRY",
      sentiment: "NEGATIVE",
      processed_at: "2026-04-27T15:10:00Z",
      body_preview: "The client is asking for a revised rollout date and a direct owner for the remaining integration blockers.",
    },
    {
      email_id: "pri-3",
      subject: "Invoice exception for April services",
      sender: "Finance Desk <ap@lakesidepartners.com>",
      urgency_label: "Needed Review",
      category: "INVOICE",
      sentiment: "NEUTRAL",
      processed_at: "2026-04-27T12:25:00Z",
      body_preview: "Line item three appears to exceed the approved amount and needs confirmation before payment can be released.",
    },
  ],
};

const DEMO_DRAFTS = {
  drafts: [
    {
      id: "dr-1",
      subject: "Re: Contract redlines needed before tomorrow’s board packet",
      sender: "Alicia Grant <alicia@northpeak.com>",
      tone: "professional",
      draft_content: "Hi Alicia,\n\nI’m reviewing the revised terms now and will send consolidated redlines before 9 AM tomorrow so legal has time to finalize the board packet. I’ll call out any points that need a quick decision from your side.\n\nBest,\n[Your Name]",
    },
    {
      id: "dr-2",
      subject: "Re: Customer escalation on delayed onboarding timeline",
      sender: "Rahul Menon <rahul@customerhq.io>",
      tone: "direct",
      draft_content: "Hi Rahul,\n\nThanks for flagging this. I’m aligning the remaining owners today and will send you an updated onboarding timeline with clear next steps and one accountable point of contact by end of day.\n\nBest,\n[Your Name]",
    },
  ],
};

const DEMO_ACTIONS = {
  items: [
    { id: "ac-1", task: "Review legal redlines and return notes before 9 AM", priority: "HIGH", due_date: "Tomorrow 9:00 AM" },
    { id: "ac-2", task: "Send revised onboarding plan to CustomerHQ", priority: "HIGH", due_date: "Today EOD" },
    { id: "ac-3", task: "Validate April invoice exception with finance", priority: "MEDIUM", due_date: "This afternoon" },
    { id: "ac-4", task: "Clear low-value newsletter subscriptions", priority: "LOW", due_date: "This week" },
  ],
};

const DEMO_REPORTS = {
  reports: [
    {
      filename: "report_20260427_1720.md",
      created_at: Date.parse("2026-04-27T17:20:00Z") / 1000,
      size: 18240,
      urgency_summary: { label: "Important", color: "red" },
    },
    {
      filename: "report_20260426_0845.md",
      created_at: Date.parse("2026-04-26T08:45:00Z") / 1000,
      size: 16410,
      urgency_summary: { label: "Review Needed", color: "orange" },
    },
  ],
};

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }

  return response.json();
}

function formatDate(value) {
  if (!value) return "No timestamp";
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

function useRemote(loader, fallback, demoData) {
  const [state, setState] = useState({ data: fallback, loading: true, error: "" });

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: "" }));
    loader()
      .then((data) => {
        if (active) setState({ data, loading: false, error: "" });
      })
      .catch((error) => {
        if (active) {
          setState({
            data: demoData,
            loading: false,
            error: "Local preview mode: live API unavailable",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [loader, demoData]);

  return state;
}

function GlowBackdrop() {
  return html`
    <div className="backdrop-layer" aria-hidden="true">
      <div className="mesh mesh-a"></div>
      <div className="mesh mesh-b"></div>
      <div className="mesh mesh-c"></div>
      <div className="grid-fade"></div>
    </div>
  `;
}

function HeroGraphic() {
  return html`
    <div className="hero-visual" aria-hidden="true">
      <div className="orbital orbital-a"></div>
      <div className="orbital orbital-b"></div>
      <div className="orbital orbital-c"></div>
      <svg viewBox="0 0 480 480" className="signal-svg">
        <defs>
          <linearGradient id="signalGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#8ff3d7"></stop>
            <stop offset="50%" stopColor="#3ec7b7"></stop>
            <stop offset="100%" stopColor="#ffb877"></stop>
          </linearGradient>
        </defs>
        <circle cx="240" cy="240" r="150" className="signal-ring"></circle>
        <circle cx="240" cy="240" r="104" className="signal-ring faint"></circle>
        <path d="M96 262 C154 208, 216 315, 272 231 S384 157, 420 207" className="signal-line"></path>
        <path d="M112 176 C162 122, 228 207, 272 161 S360 115, 396 144" className="signal-line secondary"></path>
        <g className="signal-nodes">
          <circle cx="96" cy="262" r="7"></circle>
          <circle cx="212" cy="283" r="8"></circle>
          <circle cx="320" cy="197" r="9"></circle>
          <circle cx="420" cy="207" r="7"></circle>
        </g>
      </svg>
      <div className="hero-chip chip-a">Signal clarity</div>
      <div className="hero-chip chip-b">Autonomous cadence</div>
    </div>
  `;
}

function Sidebar({ activeView, onChange }) {
  const items = [
    ["overview", "Overview"],
    ["inbox", "Inbox"],
    ["drafts", "Drafts"],
    ["actions", "Actions"],
    ["reports", "Reports"],
    ["compose", "Compose"],
  ];

  return html`
    <aside className="sidebar-shell">
      <div className="brand-lockup">
        <div className="brand-mark"><span></span></div>
        <div>
          <div className="brand-name">WorkflowAI</div>
          <div className="brand-sub">Inbox Intelligence Suite</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        ${items.map(
          ([key, label]) => html`
            <button
              key=${key}
              type="button"
              className=${classNames("nav-link", activeView === key && "active")}
              onClick=${() => onChange(key)}
            >
              <span className="nav-dot"></span>
              ${label}
            </button>
          `
        )}
      </nav>

      <div className="sidebar-note">
        Human-grade workflow design with a calmer command surface and stronger visual hierarchy.
      </div>
    </aside>
  `;
}

function StatCard({ label, value, tone, detail }) {
  return html`
    <div className=${classNames("stat-card-react", tone)}>
      <div className="stat-card-head">
        <span>${label}</span>
        <div className="stat-card-spark">
          <i></i><i></i><i></i><i></i>
        </div>
      </div>
      <div className="stat-card-value">${value}</div>
      <div className="stat-card-detail">${detail}</div>
    </div>
  `;
}

function DistributionPanel({ title, dataMap, toneClass }) {
  const rows = Object.entries(dataMap || {}).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const max = rows.length ? Math.max(...rows.map(([, value]) => value)) : 1;

  return html`
    <section className="panel">
      <div className="panel-header"><h3>${title}</h3></div>
      <div className="distribution-list">
        ${
          rows.length === 0
            ? html`<div className="empty-inline">No data yet</div>`
            : rows.map(
                ([key, value]) => html`
                  <div key=${key} className="distribution-row">
                    <div className="distribution-meta">
                      <span>${key.replace(/_/g, " ")}</span>
                      <strong>${value}</strong>
                    </div>
                    <div className="distribution-track">
                      <div
                        className=${classNames("distribution-fill", toneClass)}
                        style=${{ width: `${Math.max((value / max) * 100, 6)}%` }}
                      ></div>
                    </div>
                  </div>
                `
              )
        }
      </div>
    </section>
  `;
}

function RunList({ runs }) {
  return html`
    <section className="panel">
      <div className="panel-header"><h3>Recent workflow runs</h3></div>
      <div className="run-list">
        ${
          runs.length === 0
            ? html`<div className="empty-inline">No workflow runs found</div>`
            : runs.map(
                (run) => html`
                  <div key=${run.run_id} className="run-row-react">
                    <div>
                      <div className="run-row-id">${run.run_id.slice(0, 10)}</div>
                      <div className="run-row-time">${formatDate(run.started_at)}</div>
                    </div>
                    <div className=${classNames("pill", `status-${run.status}`)}>${run.status}</div>
                    <div className="run-row-count">${run.emails_processed} emails</div>
                  </div>
                `
              )
        }
      </div>
    </section>
  `;
}

function PriorityInbox({ emails }) {
  return html`
    <section className="panel panel-wide">
      <div className="panel-header"><h3>Priority inbox</h3></div>
      <div className="stack-list">
        ${
          emails.length === 0
            ? html`<div className="empty-inline">No priority messages available</div>`
            : emails.slice(0, 5).map(
                (email) => html`
                  <article key=${email.email_id} className="mail-card">
                    <div className="mail-card-top">
                      <div>
                        <h4>${email.subject}</h4>
                        <p>${email.sender}</p>
                      </div>
                      <div className=${classNames("pill soft", email.urgency_label === "Important" ? "hot" : email.urgency_label === "Needed Review" ? "warm" : "cool")}>
                        ${email.urgency_label}
                      </div>
                    </div>
                    <div className="mail-preview">${email.body_preview || "No preview available."}</div>
                  </article>
                `
              )
        }
      </div>
    </section>
  `;
}

function OverviewView({ summaryState, runsState, inboxState }) {
  const summary = summaryState.data || {};
  const stats = [
    ["Emails processed", summary.total_emails || 0, "mint", "Across recent workflow activity"],
    ["Success rate", `${summary.success_rate || 0}%`, "amber", `${summary.successful_runs || 0} successful runs`],
    ["Active actions", summary.active_actions || 0, "coral", "Open next-step items waiting on attention"],
    ["Draft replies", summary.total_drafts || 0, "aqua", "AI-assisted drafts ready to review"],
  ];

  return html`
    <div className="view-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <div className="eyebrow">Autonomous email intelligence</div>
          <h1>A premium cockpit for inbox signal, follow-through, and team clarity.</h1>
          <p>
            Track what matters, surface urgency with more confidence, and move from incoming noise to visible action without the interface feeling cold or mechanical.
          </p>
          <div className="hero-tags">
            <span>Priority triage</span>
            <span>Draft generation</span>
            <span>Action extraction</span>
          </div>
        </div>
        <${HeroGraphic} />
      </section>

      <section className="stats-grid-react">
        ${stats.map(
          ([label, value, tone, detail]) => html`
            <${StatCard} key=${label} label=${label} value=${value} tone=${tone} detail=${detail} />
          `
        )}
      </section>

      <section className="content-grid two-up">
        <${DistributionPanel} title="Category distribution" dataMap=${summary.category_distribution} toneClass="mint" />
        <${DistributionPanel} title="Sentiment distribution" dataMap=${summary.sentiment_distribution} toneClass="coral" />
      </section>

      <section className="content-grid two-up">
        <${RunList} runs=${runsState.data || []} />
        <${PriorityInbox} emails=${(inboxState.data && inboxState.data.emails) || []} />
      </section>
    </div>
  `;
}

function InboxView({ inboxState }) {
  const emails = (inboxState.data && inboxState.data.emails) || [];
  return html`
    <div className="view-shell">
      <section className="section-head">
        <div>
          <div className="eyebrow">Inbox</div>
          <h2>Priority-led message review</h2>
        </div>
      </section>
      <section className="stack-list">
        ${
          emails.length === 0
            ? html`<div className="panel"><div className="empty-inline">No inbox items available</div></div>`
            : emails.map(
                (email) => html`
                  <article key=${email.email_id} className="mail-card deluxe">
                    <div className="mail-card-top">
                      <div>
                        <h4>${email.subject}</h4>
                        <p>${email.sender}</p>
                      </div>
                      <div className="mail-badge-set">
                        <span className="pill soft neutral">${email.category.replace(/_/g, " ")}</span>
                        <span className=${classNames("pill soft", email.urgency_label === "Important" ? "hot" : email.urgency_label === "Needed Review" ? "warm" : "cool")}>
                          ${email.urgency_label}
                        </span>
                      </div>
                    </div>
                    <div className="mail-preview">${email.body_preview || "No preview available."}</div>
                    <div className="mail-meta">
                      <span>${formatDate(email.processed_at || email.date)}</span>
                      <span>${email.sentiment}</span>
                    </div>
                  </article>
                `
              )
        }
      </section>
    </div>
  `;
}

function DraftsView({ draftsState }) {
  const drafts = (draftsState.data && draftsState.data.drafts) || [];
  return html`
    <div className="view-shell">
      <section className="section-head">
        <div>
          <div className="eyebrow">Drafts</div>
          <h2>Reply suggestions that feel polished before you touch them</h2>
        </div>
      </section>
      <section className="card-grid">
        ${
          drafts.length === 0
            ? html`<div className="panel"><div className="empty-inline">No drafts generated yet</div></div>`
            : drafts.map(
                (draft) => html`
                  <article key=${draft.id} className="panel draft-panel">
                    <div className="panel-header">
                      <h3>${draft.subject || "Reply Draft"}</h3>
                      <span className="pill soft neutral">${draft.tone || "professional"}</span>
                    </div>
                    <div className="draft-to">To ${draft.sender || "Unknown sender"}</div>
                    <div className="draft-body">${draft.draft_content}</div>
                  </article>
                `
              )
        }
      </section>
    </div>
  `;
}

function ActionsView({ actionsState }) {
  const items = (actionsState.data && actionsState.data.items) || [];
  const columns = {
    HIGH: items.filter((item) => item.priority === "HIGH"),
    MEDIUM: items.filter((item) => item.priority === "MEDIUM"),
    LOW: items.filter((item) => item.priority === "LOW"),
  };

  return html`
    <div className="view-shell">
      <section className="section-head">
        <div>
          <div className="eyebrow">Actions</div>
          <h2>Next steps laid out with visible priority</h2>
        </div>
      </section>
      <section className="kanban-grid">
        ${Object.entries(columns).map(
          ([priority, bucket]) => html`
            <div key=${priority} className="panel kanban-column">
              <div className="panel-header"><h3>${priority} priority</h3></div>
              <div className="kanban-stack">
                ${
                  bucket.length === 0
                    ? html`<div className="empty-inline">No items</div>`
                    : bucket.map(
                        (item) => html`
                          <article key=${item.id} className="action-block">
                            <strong>${item.task}</strong>
                            <span>${item.due_date || "No due date"}</span>
                          </article>
                        `
                      )
                }
              </div>
            </div>
          `
        )}
      </section>
    </div>
  `;
}

function ReportsView({ reportsState }) {
  const reports = (reportsState.data && reportsState.data.reports) || [];
  return html`
    <div className="view-shell">
      <section className="section-head">
        <div>
          <div className="eyebrow">Reports</div>
          <h2>Executive-ready artifacts with better visual presence</h2>
        </div>
      </section>
      <section className="card-grid">
        ${
          reports.length === 0
            ? html`<div className="panel"><div className="empty-inline">No reports found</div></div>`
            : reports.map(
                (report) => html`
                  <article key=${report.filename} className="panel report-panel">
                    <div className="report-glow"></div>
                    <div className="panel-header">
                      <h3>${report.filename}</h3>
                      <span className=${classNames("pill soft", report.urgency_summary?.color === "red" ? "hot" : report.urgency_summary?.color === "orange" ? "warm" : "cool")}>
                        ${report.urgency_summary?.label || "Routine"}
                      </span>
                    </div>
                    <div className="report-meta">${formatDate(report.created_at * 1000)}</div>
                    <div className="report-size">${Math.round((report.size || 0) / 1024)} KB</div>
                  </article>
                `
              )
        }
      </section>
    </div>
  `;
}

function ComposeView() {
  const [form, setForm] = useState({
    to: "",
    intent: "",
    tone: "professional",
    context: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch("/compose", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setResult(data);
    } catch (err) {
      setResult(buildLocalDraft(form));
      setError("Local preview mode: compose API unavailable");
    } finally {
      setLoading(false);
    }
  }

  return html`
    <div className="view-shell">
      <section className="section-head">
        <div>
          <div className="eyebrow">Compose</div>
          <h2>Generate a polished email with a more human surface</h2>
        </div>
      </section>
      <section className="compose-grid">
        <form className="panel form-panel" onSubmit=${onSubmit}>
          <label>
            Recipient
            <input value=${form.to} onInput=${(e) => setForm({ ...form, to: e.target.value })} placeholder="recipient@example.com" />
          </label>
          <label>
            Intent
            <textarea value=${form.intent} onInput=${(e) => setForm({ ...form, intent: e.target.value })} placeholder="What should the email achieve?" rows="5"></textarea>
          </label>
          <label>
            Tone
            <select value=${form.tone} onChange=${(e) => setForm({ ...form, tone: e.target.value })}>
              <option value="professional">Professional</option>
              <option value="friendly">Friendly</option>
              <option value="direct">Direct</option>
              <option value="persuasive">Persuasive</option>
              <option value="formal">Formal</option>
            </select>
          </label>
          <label>
            Context
            <textarea value=${form.context} onInput=${(e) => setForm({ ...form, context: e.target.value })} placeholder="Extra context, deadlines, or background" rows="4"></textarea>
          </label>
          <button className="primary-cta" type="submit" disabled=${loading}>
            ${loading ? "Composing..." : "Generate Email"}
          </button>
          ${error ? html`<div className="error-inline">${error}</div>` : null}
        </form>

        <div className="panel compose-output">
          ${
            result
              ? html`
                  <div className="eyebrow">Generated output</div>
                  <h3>${result.subject}</h3>
                  <div className="compose-to-line">To ${result.to}</div>
                  <div className="compose-result-body">${result.body}</div>
                `
              : html`
                  <div className="compose-empty">
                    <${HeroGraphic} />
                    <div>
                      <h3>Crafted drafts appear here</h3>
                      <p>Use the form to generate a polished message with better tone, structure, and pacing.</p>
                    </div>
                  </div>
                `
          }
        </div>
      </section>
    </div>
  `;
}

function buildLocalDraft(form) {
  const greeting = form.tone === "formal" ? "Dear" : "Hi";
  const opening =
    form.tone === "direct"
      ? "I’m reaching out with a concise update."
      : form.tone === "friendly"
        ? "Hope you’re doing well."
        : "I wanted to follow up with a clear update.";

  const subject = form.intent
    ? form.intent.slice(0, 72)
    : "Follow-up";

  return {
    to: form.to || "recipient@example.com",
    subject,
    body: `${greeting},\n\n${opening} ${form.intent || "Here is the requested note."}${form.context ? `\n\nContext: ${form.context}` : ""}\n\nPlease let me know if you would like me to adjust anything before sending.\n\nBest,\n[Your Name]`,
  };
}

function ErrorBanner({ errors }) {
  const items = errors.filter(Boolean);
  if (!items.length) return null;
  return html`
    <div className="error-banner">
      ${items.map((item, index) => html`<span key=${`${item}-${index}`}>${item}</span>`)}
    </div>
  `;
}

function App() {
  const [view, setView] = useState("overview");

  const summaryLoader = useCallback(() => apiFetch("/analytics/summary?days=7"), []);
  const runsLoader = useCallback(() => apiFetch("/runs?limit=6"), []);
  const inboxLoader = useCallback(() => apiFetch("/emails/priority-inbox?limit=8"), []);
  const draftsLoader = useCallback(() => apiFetch("/drafts?limit=12"), []);
  const actionsLoader = useCallback(() => apiFetch("/actions?completed=false"), []);
  const reportsLoader = useCallback(() => apiFetch("/reports"), []);

  const summaryState = useRemote(summaryLoader, {}, DEMO_SUMMARY);
  const runsState = useRemote(runsLoader, [], DEMO_RUNS);
  const inboxState = useRemote(inboxLoader, { emails: [] }, DEMO_PRIORITY);
  const draftsState = useRemote(draftsLoader, { drafts: [] }, DEMO_DRAFTS);
  const actionsState = useRemote(actionsLoader, { items: [] }, DEMO_ACTIONS);
  const reportsState = useRemote(reportsLoader, { reports: [] }, DEMO_REPORTS);

  const allErrors = useMemo(
    () => [
      summaryState.error,
      runsState.error,
      inboxState.error,
      draftsState.error,
      actionsState.error,
      reportsState.error,
    ],
    [summaryState.error, runsState.error, inboxState.error, draftsState.error, actionsState.error, reportsState.error]
  );

  return html`
    <div className="app-shell">
      <${GlowBackdrop} />
      <${Sidebar} activeView=${view} onChange=${setView} />
      <main className="main-shell">
        <header className="topbar">
          <div>
            <div className="topbar-label">Premium workflow surface</div>
            <div className="topbar-title">Human-centered control room</div>
          </div>
          <div className="topbar-pills">
            <span>React-driven</span>
            <span>Animated graphics</span>
            <span>API-connected</span>
          </div>
        </header>

        <${ErrorBanner} errors=${allErrors} />

        ${view === "overview" ? html`<${OverviewView} summaryState=${summaryState} runsState=${runsState} inboxState=${inboxState} />` : null}
        ${view === "inbox" ? html`<${InboxView} inboxState=${inboxState} />` : null}
        ${view === "drafts" ? html`<${DraftsView} draftsState=${draftsState} />` : null}
        ${view === "actions" ? html`<${ActionsView} actionsState=${actionsState} />` : null}
        ${view === "reports" ? html`<${ReportsView} reportsState=${reportsState} />` : null}
        ${view === "compose" ? html`<${ComposeView} />` : null}
      </main>
    </div>
  `;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
