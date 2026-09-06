import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SIH26100: GeM Bid Compliance Platform",
  description: "AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased min-h-screen flex flex-col">
        <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur-md sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-6">
              <Link href="/" className="flex items-center space-x-3">
                <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center font-bold text-white shadow-md shadow-blue-500/20">
                  GeM
                </div>
                <div>
                  <h1 className="font-semibold text-sm sm:text-base text-slate-100">
                    SIH26100 • GeM Compliance Verification
                  </h1>
                  <p className="text-xs text-slate-400">Bid Evaluation Platform</p>
                </div>
              </Link>
              <nav className="hidden sm:flex items-center space-x-1">
                <Link
                  href="/"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition"
                >
                  Dashboard
                </Link>
                <Link
                  href="/tenders/new"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition"
                >
                  Upload Tender
                </Link>
              </nav>
            </div>
            <div className="flex items-center space-x-3">
              <Link
                href="/tenders/new"
                className="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition shadow-sm"
              >
                + New Tender
              </Link>
              <span className="hidden md:inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-blue-950/80 text-blue-400 border border-blue-800/60">
                ● Day 2: AI Clause Extraction
              </span>
            </div>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
          {children}
        </main>
      </body>
    </html>
  );
}
