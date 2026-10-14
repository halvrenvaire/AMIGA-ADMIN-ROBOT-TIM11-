/** Aset brand resmi amiga (frontend/public/brand), dari Logo-AMIGA-2025. */

export function Logo({ height = 34 }: { height?: number }) {
  // alignSelf: tidak ikut diregangkan bila induknya flex kolom; rasio asli 250x78
  return <img src="/brand/logo-amiga.png" alt="amiga" height={height} width={Math.round((height * 250) / 78)}
              style={{ display: "block", alignSelf: "flex-start", flex: "none" }} />;
}

/** Semanggi merah muda dari logo amiga, untuk aksen dekoratif. */
export function Clover({ size = 28, className, style }: { size?: number; className?: string; style?: React.CSSProperties }) {
  return <img src="/brand/semanggi.png" alt="" aria-hidden="true" width={size} height={size} className={className} style={style} />;
}
