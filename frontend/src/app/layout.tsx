import type { Metadata } from 'next';
import './globals.css';
import { TopNavbar } from '@/components/layout/top-navbar';

export const metadata: Metadata = {
  title: '新一代信息技术岗位图谱系统',
  description: '基于多源数据的岗位能力图谱与动态演化分析平台',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="bg-[#F8FAFC] text-slate-900 antialiased">
        <TopNavbar />
        <div className="pt-14 flex min-h-screen">
          {children}
        </div>
      </body>
    </html>
  );
}
