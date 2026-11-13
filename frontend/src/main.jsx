import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './app/App.jsx';
import './styles/theme.css';
import './styles/globals.css';
import './styles/catalog.css';
import './styles/recommendations.css';
import './styles/insights.css';

createRoot(document.getElementById('root')).render(
  <React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>,
);
