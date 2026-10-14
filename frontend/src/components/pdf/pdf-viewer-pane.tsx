'use client';

import React, { useState } from 'react';
import { ZoomIn, ZoomOut, Maximize2, ExternalLink, Download, FileText } from 'lucide-react';

interface PdfViewerPaneProps {
  pdfUrl: string;
  originalFileName: string;
  filePageCount: number;
}

export function PdfViewerPane({
  pdfUrl,
  originalFileName,
  filePageCount,
}: PdfViewerPaneProps) {
  const [zoomLevel, setZoomLevel] = useState<number>(100);

  const handleZoomIn = () => {
    setZoomLevel((prev) => Math.min(200, prev + 25));
  };

  const handleZoomOut = () => {
    setZoomLevel((prev) => Math.max(50, prev - 25));
  };

  const handleFitToWidth = () => {
    setZoomLevel(100);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border-r border-slate-700 select-none">
      {/* Viewer Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-800 border-b border-slate-700 text-slate-200">
        <div className="flex items-center gap-2 truncate">
          <FileText className="w-4 h-4 text-blue-400 flex-shrink-0" />
          <span className="text-xs font-medium truncate max-w-[200px]" title={originalFileName}>
            {originalFileName}
          </span>
          <span className="text-[11px] text-slate-400 px-1.5 py-0.5 rounded bg-slate-700 font-mono">
            {filePageCount} Hal
          </span>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleZoomOut}
            disabled={zoomLevel <= 50}
            className="p-1 rounded hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400"
            title="Perkecil (-25%)"
          >
            <ZoomOut className="w-4 h-4" />
          </button>

          <span className="text-xs font-mono font-semibold px-1.5 min-w-[45px] text-center text-slate-200">
            {zoomLevel}%
          </span>

          <button
            type="button"
            onClick={handleZoomIn}
            disabled={zoomLevel >= 200}
            className="p-1 rounded hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400"
            title="Perbesar (+25%)"
          >
            <ZoomIn className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={handleFitToWidth}
            className="p-1 rounded hover:bg-slate-700 text-slate-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400 ml-1"
            title="Sesuaikan Lebar (100%)"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>

          <div className="h-4 w-px bg-slate-700 mx-1" />

          <a
            href={pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1 rounded hover:bg-slate-700 text-slate-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400"
            title="Buka Dokumen di Tab Baru"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>

          <a
            href={pdfUrl}
            download={originalFileName}
            className="p-1 rounded hover:bg-slate-700 text-slate-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400"
            title="Unduh Berkas PDF Asli"
          >
            <Download className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* PDF Viewport (Isolated Scroll) */}
      <div className="flex-1 overflow-auto bg-slate-950 p-4 flex justify-center items-start">
        <div
          className="transition-transform duration-150 origin-top bg-white rounded-lg shadow-2xl overflow-hidden"
          style={{
            width: `${zoomLevel}%`,
            minWidth: '600px',
            maxWidth: '1200px',
            height: '100%',
            minHeight: '800px',
          }}
        >
          <iframe
            src={`${pdfUrl}#toolbar=0&navpanes=0`}
            title={`Pratinjau PDF: ${originalFileName}`}
            className="w-full h-full border-0 rounded-lg min-h-[850px]"
          />
        </div>
      </div>
    </div>
  );
}
