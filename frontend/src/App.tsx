import React, { useState } from 'react';
import { Shell } from '@/components/layout/Shell';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import { Alerts } from '@/pages/Alerts';
import { FoundationOverview } from '@/pages/FoundationOverview';
import { TacticalMap } from '@/pages/TacticalMap';

export const App: React.FC = () => {
  const [activeNav, setActiveNav] = useState<string>('cctv');
  const [targetCameraId, setTargetCameraId] = useState<string | null>(null);

  const handleSelectCameraFromMap = (cameraId: string) => {
    setTargetCameraId(cameraId);
    setActiveNav('cctv');
  };

  const renderContent = () => {
    switch (activeNav) {
      case 'cctv':
        return <CCTVMonitoring initialCameraId={targetCameraId} />;
      case 'alerts':
        return <Alerts />;
      case 'map':
        return <TacticalMap onSelectCamera={handleSelectCameraFromMap} />;
      case 'foundation':
        return <FoundationOverview />;
      default:
        return <CCTVMonitoring initialCameraId={targetCameraId} />;
    }
  };

  return (
    <Shell activeNav={activeNav} onNavChange={setActiveNav}>
      {renderContent()}
    </Shell>
  );
};

export default App;
