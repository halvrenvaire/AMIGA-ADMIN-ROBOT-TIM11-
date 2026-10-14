import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, homePath, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AdminClients, AdminUsers } from "./pages/Admin";
import { DocumentPage } from "./pages/DocumentPage";
import { HistoryPage } from "./pages/HistoryPage";
import { Histories, MyReviews, SearchResults, Submissions, Vouchers } from "./pages/Lists";
import { Login } from "./pages/Login";
import { Queue } from "./pages/Queue";
import { Upload } from "./pages/Upload";
import { VoucherPage } from "./pages/VoucherPage";
import type { Role } from "./types";

function Protected({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading, has } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  // Tampilan ikut dibatasi; pengecekan sebenarnya tetap di server
  if (roles && !has(...roles)) return <Navigate to={homePath(user.roles)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={user ? homePath(user.roles) : "/login"} replace />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><Layout /></Protected>}>
            <Route index element={<Home />} />
            <Route path="antrean" element={<Protected roles={["SERVICE_LEAD", "FINANCE_REVIEWER"]}><Queue /></Protected>} />
            <Route path="peninjauan" element={<Protected roles={["FINANCE_REVIEWER"]}><MyReviews /></Protected>} />
            <Route path="unggah" element={<Protected roles={["PIC_KLIEN", "INTAKE_SUPPORT"]}><Upload /></Protected>} />
            <Route path="pengajuan" element={<Protected roles={["PIC_KLIEN", "INTAKE_SUPPORT"]}><Submissions /></Protected>} />
            <Route path="voucher" element={<Vouchers />} />
            <Route path="riwayat" element={<Histories />} />
            <Route path="cari" element={<SearchResults />} />
            <Route path="dokumen/:id" element={<DocumentPage />} />
            <Route path="dokumen/:id/voucher" element={<VoucherPage />} />
            <Route path="dokumen/:id/riwayat" element={<HistoryPage />} />
            <Route path="admin/pengguna" element={<Protected roles={["SYSTEM_ADMIN"]}><AdminUsers /></Protected>} />
            <Route path="admin/klien" element={<Protected roles={["SYSTEM_ADMIN"]}><AdminClients /></Protected>} />
            <Route path="*" element={<Home />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
