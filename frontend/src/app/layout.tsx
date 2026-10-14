import type { Metadata } from 'next';
import './globals.css';
import { QueryProvider } from '../components/providers/query-provider';

export const metadata: Metadata = {
  title: 'AMIGA Robot Admin',
  description: 'Intelligent Vendor Invoice-to-Voucher Processing System',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body className="antialiased selection:bg-blue-100 selection:text-blue-900 bg-[#F8F9FB] text-[#0B3558] min-h-screen">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
