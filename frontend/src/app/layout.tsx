import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "GeM Bid Compliance Verification Platform • SIH26100",
  description: "AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 antialiased min-h-screen flex flex-col font-sans">
        {/* Government Top Bar */}
        <div className="bg-slate-900 text-slate-200 text-[11px] px-4 py-1 border-b border-slate-800">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="font-medium tracking-wide">GOVERNMENT OF INDIA • GeM PROCUREMENT VERIFICATION</span>
            </div>
            <div className="flex items-center space-x-4 text-slate-400">
              <span>SIH 2026 Problem ID: SIH26100</span>
              <span>•</span>
              <span className="text-emerald-400 font-medium">Platform: Online</span>
            </div>
          </div>
        </div>

        {/* Main Navigation Header */}
        <header className="border-b border-slate-200 bg-white shadow-sm sticky top-0 z-40">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-6">
              <Link href="/" className="flex items-center space-x-3 group">
                <div className="h-9 w-9 rounded-md bg-blue-900 flex items-center justify-center font-bold text-white text-sm shadow-sm tracking-wider">
                  GeM
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm sm:text-base text-slate-900 tracking-tight">
                      BidGuard AI
                    </span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-blue-50 text-blue-800 border border-blue-200">
                      v1.0-RC
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 font-medium">
                    Integrated Bid Compliance Verification Platform
                  </p>
                </div>
              </Link>

              <nav className="hidden md:flex items-center space-x-1 pl-4 border-l border-slate-200">
                <Link
                  href="/"
                  className="px-3 py-1.5 rounded-md text-xs font-semibold text-slate-700 hover:text-blue-900 hover:bg-slate-100 transition"
                >
                  Tenders
                </Link>
                <Link
                  href="/tenders/new"
                  className="px-3 py-1.5 rounded-md text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                >
                  Upload Tender PDF
                </Link>
              </nav>
            </div>

            <div className="flex items-center space-x-3">
              <span className="hidden lg:inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                <span className="w-2 h-2 rounded-full bg-emerald-500 mr-1.5 inline-block" />
                Hybrid Verification Active
              </span>

              <Link
                href="/tenders/new"
                className="inline-flex items-center px-3.5 py-1.5 rounded-md text-xs font-semibold bg-blue-900 hover:bg-blue-800 text-white transition shadow-sm"
              >
                + Create Tender
              </Link>
            </div>
          </div>
        </header>

        {/* Main Application Area */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full">
          {children}
        </main>

        {/* Official Footer */}
        <footer className="border-t border-slate-200 bg-white text-slate-500 text-xs py-5 mt-auto">
          <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
            <div>
              <strong className="text-slate-700 font-semibold">SIH26100: Bid Compliance Verification Platform</strong> — Designed for GeM Public Procurement
            </div>
            <div className="text-slate-400 text-[11px]">
              Strictly Source-Grounded Evidence • Clause-Scoped Contradiction Detection • Deterministic Verification
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
