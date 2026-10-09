import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...a) => twMerge(clsx(a));

export function Button({ className, variant = "primary", ...p }) {
  const v = {
    primary: "bg-tiffany text-ink hover:bg-tiffany-hover shadow-sm",
    dark: "bg-ink text-white hover:bg-slate-800",
    outline: "border border-slate-300 bg-white text-ink hover:bg-slate-50",
  }[variant];
  return <button className={cn("inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full text-sm font-semibold whitespace-nowrap transition-[background-color,transform,box-shadow] duration-150 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tiffany/50", v, className)} {...p} />;
}

export function Field({ label, error, children }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <div className="mt-1">{children}</div>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Input({ className, ...p }) {
  return <input className={cn("w-full h-11 rounded-xl border border-slate-200 bg-white px-3.5 text-sm outline-none transition-[border-color,box-shadow] focus:border-tiffany focus:ring-2 focus:ring-tiffany/25", className)} {...p} />;
}

export function Select({ className, children, ...p }) {
  return <select className={cn("w-full h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/25", className)} {...p}>{children}</select>;
}

export function Logo({ className }) {
  return <span className={cn("font-display font-extrabold tracking-tight text-ink whitespace-nowrap", className)}>CRM<span className="text-tiffany">Event</span> <span className="font-semibold text-slate-500">Partner</span></span>;
}
