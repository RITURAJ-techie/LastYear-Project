import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { BarChart3, Brain, Database, Sparkles } from "lucide-react";
import { useAuth } from "../auth";
import { errMsg } from "../api";
import { Button, ErrorBox, Field, Input } from "../components/ui";

export default function Login() {
  const { user, login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const features = [
    { icon: Database, t: "Multi-source ETL", d: "CSV, Excel, JSON, SQL databases and REST APIs into one warehouse" },
    { icon: Brain, t: "Automatic understanding", d: "Detects types, roles and relationships; cleans and scores data quality" },
    { icon: BarChart3, t: "Auto dashboards", d: "KPIs, trends, forecasts and interactive charts generated for you" },
    { icon: Sparkles, t: "Actionable insights", d: "Anomalies, drivers and recommendations in plain language" },
  ];

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-[#17153a] p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <img src="/logo.svg" className="h-9 w-9" alt="" />
          <span className="text-lg font-semibold">InsightFlow AI</span>
        </div>
        <div>
          <h1 className="text-3xl font-semibold leading-tight">Turn raw data into decisions —<br />without writing a line of code.</h1>
          <p className="mt-3 max-w-md text-sm text-white/70">An AI-powered universal analytics, visualization and decision-support platform built on a modern data warehouse.</p>
          <div className="mt-10 grid grid-cols-2 gap-5">
            {features.map((f) => (
              <div key={f.t}>
                <f.icon className="h-5 w-5 text-[#9085e9]" />
                <div className="mt-2 text-sm font-medium">{f.t}</div>
                <div className="mt-0.5 text-xs text-white/60">{f.d}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="text-xs text-white/40">Modern Data Warehouse–Driven Decision Support & Analytics Framework</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <div className="mb-6 lg:hidden"><img src="/logo.svg" className="h-10 w-10" alt="" /></div>
          <div>
            <h2 className="text-xl font-semibold">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
            <p className="mt-1 text-sm text-muted">{mode === "login" ? "Sign in to your analytics workspace" : "Start analysing your data in minutes"}</p>
          </div>
          {error && <ErrorBox>{error}</ErrorBox>}
          {mode === "register" && <Field label="Full name"><Input value={name} onChange={(e) => setName(e.target.value)} required /></Field>}
          <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></Field>
          <Field label="Password"><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} autoComplete={mode === "login" ? "current-password" : "new-password"} /></Field>
          <Button variant="primary" className="w-full" loading={busy} type="submit">{mode === "login" ? "Sign in" : "Create account"}</Button>
          {mode === "login" && (
            <button type="button" className="w-full rounded-lg border border-dashed border-line px-3 py-2 text-left text-xs text-ink2 hover:bg-surface2"
              onClick={() => { setEmail("demo@insightflow.ai"); setPassword("demo1234"); }}>
              <span className="font-medium text-ink">Try the demo workspace</span> — demo@insightflow.ai / demo1234 (click to fill)
            </button>
          )}
          <p className="text-center text-sm text-muted">
            {mode === "login" ? "New here? " : "Already have an account? "}
            <button type="button" className="font-medium text-accent" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
