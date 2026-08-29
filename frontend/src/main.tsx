import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { CreateProfile } from './pages/CreateProfile';
import { MyCard } from './pages/MyCard';
import { EditProfile } from './pages/EditProfile';
import { SOS } from './pages/SOS';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/create" element={<CreateProfile />} />
          <Route path="/card" element={<MyCard />} />
          <Route path="/edit" element={<EditProfile />} />
          <Route path="/sos" element={<SOS />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  </StrictMode>
);
