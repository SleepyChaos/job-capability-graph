import type { Metadata } from "next";
import { Sidebar } from "@/components/layout/sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "具身智能岗位能力图谱系统",
  description: "多源异构数据驱动岗位和能力图谱构建与动态演化分析",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased bg-gray-50 min-h-screen">
        <Sidebar />
        <main className="ml-60 min-h-screen">
          <div className="p-6">{children}</div>
        </main>
      </body>
    </html>
  );
}
