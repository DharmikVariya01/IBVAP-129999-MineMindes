import React, { useState } from 'react';
import { Shell } from '@/components/layout/Shell';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import { FoundationOverview } from '@/pages/FoundationOverview';

export const App: React.FC = () => {
  const [activeNav, setActiveNav] = useState<string>('cctv');

  const renderContent = () => {
    switch (activeNav) {
      case 'cctv':
        return <CCTVMonitoring />;
      case 'foundation':
        return <FoundationOverview />;
      default:
        return <CCTVMonitoring />;
    }
  };

  return (
    <Shell activeNav={activeNav} onNavChange={setActiveNav}>
      {renderContent()}
    </Shell>
  );
};

export default App;
