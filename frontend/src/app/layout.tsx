import type { Metadata } from 'next';
import '@fontsource-variable/inter';
import '@xyflow/react/dist/style.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'OpsPilot AI · Agent Operations',
  description: 'Local incident investigation, human approval and verified recovery.',
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
