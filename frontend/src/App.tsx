import React, { useState, useEffect } from 'react';
import { Shell } from '@/components/layout/Shell';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import { Alerts } from '@/pages/Alerts';
import { FoundationOverview } from '@/pages/FoundationOverview';
import { TacticalMap } from '@/pages/TacticalMap';
import { EventTimelinePage } from '@/pages/EventTimelinePage';

export const App: React.FC = () => {
  const [activeNav, setActiveNav] = useState<string>('cctv');
  const [previousNav, setPreviousNav] = useState<string>('cctv');
  const [targetCameraId, setTargetCameraId] = useState<string | null>(null);
  const [targetTrackId, setTargetTrackId] = useState<number | string | null>(null);

  // Sync hash routing if directly accessed (e.g. #/timeline/10 or #timeline)
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      if (hash.includes('timeline')) {
        const match = hash.match(/(?:timeline\/|#)?(\d+)/i);
        if (match && match[1]) {
          setTargetTrackId(match[1]);
        }
        setActiveNav('timeline');
      }
    };

    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleSelectCameraFromMap = (cameraId: string) => {
    setTargetCameraId(cameraId);
    setActiveNav('cctv');
  };

  const handleViewTimeline = (trackId: number | string) => {
    setPreviousNav(activeNav);
    setTargetTrackId(trackId);
    setActiveNav('timeline');
  };

  const handleBackFromTimeline = () => {
    setActiveNav(previousNav || 'cctv');
  };

  const renderContent = () => {
    switch (activeNav) {
      case 'cctv':
        return (
          <CCTVMonitoring
            initialCameraId={targetCameraId}
            onViewTimeline={handleViewTimeline}
          />
        );
      case 'alerts':
        return <Alerts onViewTimeline={handleViewTimeline} />;
      case 'map':
        return (
          <TacticalMap
            onSelectCamera={handleSelectCameraFromMap}
            onViewTimeline={handleViewTimeline}
          />
        );
      case 'timeline':
        return (
          <EventTimelinePage
            initialTrackId={targetTrackId}
            onBack={handleBackFromTimeline}
          />
        );
      case 'foundation':
        return <FoundationOverview />;
      default:
        return (
          <CCTVMonitoring
            initialCameraId={targetCameraId}
            onViewTimeline={handleViewTimeline}
          />
        );
    }
  };

  return (
    <Shell activeNav={activeNav} onNavChange={setActiveNav}>
      {renderContent()}
    </Shell>
  );
};

export default App;
