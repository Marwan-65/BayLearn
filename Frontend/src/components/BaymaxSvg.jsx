export default function BaymaxSvg({ size = 120, style = {} }) {
  return (
    <svg
      width={size}
      height={size * 1.4}
      viewBox="0 0 100 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={style}
    >
      {/* Head */}
      <circle cx="50" cy="32" r="24" fill="white" stroke="#D1D5DB" strokeWidth="1.5" />

      {/* Left eye */}
      <ellipse cx="42" cy="30" rx="6" ry="4.5" fill="#1F2937" />
      {/* Right eye */}
      <ellipse cx="58" cy="30" rx="6" ry="4.5" fill="#1F2937" />
      {/* Eye highlights */}
      <ellipse cx="44.5" cy="28" rx="2" ry="1.5" fill="white" />
      <ellipse cx="60.5" cy="28" rx="2" ry="1.5" fill="white" />

      {/* Mouth */}
      <line x1="44" y1="44" x2="56" y2="44" stroke="#9CA3AF" strokeWidth="1.5" strokeLinecap="round" />

      {/* Neck */}
      <rect x="43" y="55" width="14" height="8" rx="4" fill="white" stroke="#D1D5DB" strokeWidth="1.5" />

      {/* Body */}
      <ellipse cx="50" cy="98" rx="28" ry="33" fill="white" stroke="#D1D5DB" strokeWidth="1.5" />

      {/* Body mid-line */}
      <path d="M24 98 Q50 101 76 98" stroke="#E5E7EB" strokeWidth="1" fill="none" />

      {/* Left arm */}
      <ellipse
        cx="17" cy="86"
        rx="12" ry="7"
        fill="white" stroke="#D1D5DB" strokeWidth="1.5"
        transform="rotate(-20 17 86)"
      />
      {/* Right arm */}
      <ellipse
        cx="83" cy="86"
        rx="12" ry="7"
        fill="white" stroke="#D1D5DB" strokeWidth="1.5"
        transform="rotate(20 83 86)"
      />

      {/* Left leg */}
      <ellipse cx="38" cy="130" rx="11" ry="8" fill="white" stroke="#D1D5DB" strokeWidth="1.5" />
      {/* Right leg */}
      <ellipse cx="62" cy="130" rx="11" ry="8" fill="white" stroke="#D1D5DB" strokeWidth="1.5" />
    </svg>
  );
}
