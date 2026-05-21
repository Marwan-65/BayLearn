/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // BayLearn brand — lifted straight from the logo
        bay: {
          50: "#EBF7FD",
          100: "#D2EDFA",
          200: "#A5DAF4",
          300: "#78C7EF",
          400: "#4BB4E9",
          500: "#1E8FD5", // "Bay" blue — primary
          600: "#1879B3",
          700: "#135F8C",
          800: "#0E4566",
          900: "#082D43",
        },
        learn: {
          50: "#FFF5E8",
          100: "#FFE7CC",
          200: "#FFCF99",
          300: "#FFB766",
          400: "#FF9F33",
          500: "#F5A623", // "Learn" orange — accent
          600: "#D98A12",
          700: "#B36F0E",
          800: "#80500B",
          900: "#4D3008",
        },
        // Surfaces
        ink: {
          DEFAULT: "#0B1220", // deep navy (dark bg)
          muted: "#131A2B",
          elevated: "#1A2236",
          border: "rgba(255,255,255,0.08)",
        },
        cream: {
          DEFAULT: "#FFF8F0", // warm white (light bg)
          muted: "#FDF1E2",
          elevated: "#FFFFFF",
          border: "rgba(11,18,32,0.08)",
        },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', '"Syne"', "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      backgroundImage: {
        // Signature BayLearn gradient — Bay→Learn from the logo
        "bay-gradient":
          "linear-gradient(135deg, #1E8FD5 0%, #4BB4E9 40%, #F5A623 100%)",
        "bay-gradient-soft":
          "linear-gradient(135deg, rgba(30,143,213,0.15), rgba(245,166,35,0.15))",
        "bay-radial":
          "radial-gradient(60% 60% at 50% 35%, rgba(30,143,213,0.28) 0%, rgba(11,18,32,0) 70%)",
        "learn-glow":
          "radial-gradient(60% 60% at 50% 50%, rgba(245,166,35,0.35) 0%, rgba(11,18,32,0) 70%)",
        "mesh-dark":
          "radial-gradient(60% 50% at 20% 20%, rgba(30,143,213,0.20), transparent 60%), radial-gradient(50% 50% at 85% 80%, rgba(245,166,35,0.18), transparent 60%), radial-gradient(40% 40% at 50% 50%, rgba(75,180,233,0.10), transparent 70%)",
        "mesh-light":
          "radial-gradient(60% 50% at 20% 20%, rgba(30,143,213,0.18), transparent 60%), radial-gradient(50% 50% at 85% 80%, rgba(245,166,35,0.22), transparent 60%)",
      },
      boxShadow: {
        "glow-bay": "0 0 40px rgba(30,143,213,0.35)",
        "glow-learn": "0 0 40px rgba(245,166,35,0.35)",
        "glow-soft": "0 8px 32px rgba(30,143,213,0.15)",
        "card-lift": "0 12px 40px -8px rgba(11,18,32,0.25)",
      },
      animation: {
        float: "float 6s ease-in-out infinite",
        "float-slow": "float 10s ease-in-out infinite",
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
        "shimmer": "shimmer 2s linear infinite",
        "drift-up": "driftUp 20s linear infinite",
        "slide-up": "slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in": "fadeIn 0.4s ease-out",
        "scale-in": "scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0) rotate(0deg)" },
          "50%": { transform: "translateY(-16px) rotate(1.5deg)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.7", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.04)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        driftUp: {
          "0%": { transform: "translateY(100vh) translateX(0)", opacity: "0" },
          "10%": { opacity: "0.6" },
          "90%": { opacity: "0.6" },
          "100%": { transform: "translateY(-10vh) translateX(30px)", opacity: "0" },
        },
        slideUp: {
          "0%": { transform: "translateY(16px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        scaleIn: {
          "0%": { transform: "scale(0.95)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};
