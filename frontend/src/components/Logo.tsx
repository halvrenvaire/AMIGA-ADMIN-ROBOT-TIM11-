import { useState } from "react";

/** Semanggi empat daun merah muda dari logo amiga. */
export function Clover({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <g fill="#FF80B4">
        {[0, 90, 180, 270].map((r) => (
          <path key={r} transform={`rotate(${r} 20 20)`}
                d="M20 18.2C14.6 14.6 12.6 9 15.6 7.2c1.9-1.1 3.6 0 4.4 1.7.8-1.7 2.5-2.8 4.4-1.7 3 1.8 1 7.4-4.4 11z" />
        ))}
      </g>
      <path d="M21.5 21.5c2 4.5 5.5 8.5 11 11" stroke="#4497A1" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Logo amiga. Bila file logo resmi diletakkan di frontend/public/brand/logo-amiga.png, file itu yang dipakai;
 * bila tidak ada, ditampilkan semanggi + wordmark yang menyerupainya.
 */
export function Logo({ height = 34, light = false }: { height?: number; light?: boolean }) {
  const [official, setOfficial] = useState(!light);
  if (official) {
    return <img src="/brand/logo-amiga.png" alt="amiga" height={height} onError={() => setOfficial(false)} style={{ display: "block" }} />;
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }} aria-label="amiga">
      <Clover size={height} />
      <span style={{
        fontFamily: "var(--font)", fontStyle: "italic", fontWeight: 800, fontSize: height * 0.86, lineHeight: 1,
        letterSpacing: "-0.03em", color: light ? "#fff" : "var(--brand)",
      }}>amiga</span>
    </span>
  );
}
