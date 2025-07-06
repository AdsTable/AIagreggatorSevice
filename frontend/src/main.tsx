import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import MainLayout from "@components/MainLayout";
import Dashboard from "@pages/Dashboard";
import Providers from "@pages/Providers";
import Analytics from "@pages/Analytics";
import Diagnostics from "@pages/Diagnostics";
import Login from "@pages/Login";
import NotFound from "@pages/NotFound";
import "@styles/main.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/diagnostics" element={<Diagnostics />} />
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);