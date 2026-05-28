import Link from "next/link";

const links = [
  { href: "/", label: "Impact" },
  { href: "/intake", label: "New Intake" },
  { href: "/reservations", label: "P.E.T." },
  { href: "/calendar", label: "Calendar" },
  { href: "/diagnostics", label: "Diagnostics" },
  { href: "/budget", label: "Budget" },
  { href: "/events/manual", label: "Log Off-Site Event" },
  { href: "/surveys", label: "Surveys" },
  { href: "/alerts", label: "Alerts" },
];

export function Nav() {
  return (
    <header className="border-b border-cgcs-line bg-white">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-4">
        <Link href="/" className="font-semibold text-cgcs-ink">
          CGCS Dashboard
        </Link>
        <nav className="flex gap-4 text-sm text-cgcs-mute">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-cgcs-ink">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
