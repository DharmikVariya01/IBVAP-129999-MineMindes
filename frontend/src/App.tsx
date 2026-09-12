import React, { useState } from 'react';
import { Shell } from '@/components/layout/Shell';
import { FoundationOverview } from '@/pages/FoundationOverview';

export const App: React.FC = () => {
  const [activeNav, setActiveNav] = useState('foundation');

  return (
    <Shell activeNav={activeNav} onNavChange={setActiveNav}>
      <FoundationOverview />
    </Shell>
  );
};

export default App;
