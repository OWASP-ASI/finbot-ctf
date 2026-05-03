/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./finbot/**/*.{html,js,py}",
    "./finbot/apps/**/*.{html,js}",
    "./finbot/templates/**/*.{html,js}",
    "./finbot/static/**/*.{html,js}",
  ],
  theme: {
    extend: {
      colors: {
        // CineFlow branding colors
        'cine-gold': '#D4AF37',
        'cine-dark': '#0F0F0F',
        'cine-gray': '#1A1A1A',
        'cine-light': '#F8F8F8',
        
        // CTF colors
        'ctf-green': '#10B981',
        'ctf-dark': '#111827',
        'ctf-gray': '#374151',
        
        // Admin portal colors
        'admin-primary': '#f59e0b',
        'admin-secondary': '#d97706',
        'admin-accent': '#fbbf24',
        'admin-danger': '#ef4444',
        'admin-success': '#22c55e',
        
        // Vendor portal colors
        'vendor-primary': '#00d4ff',
        'vendor-secondary': '#7c3aed',
        'vendor-accent': '#06ffa5',
        'vendor-warning': '#ffb800',
        'vendor-danger': '#ff3366',
        
        // CTF portal colors
        'ctf-primary': '#00d4ff',
        'ctf-secondary': '#7c3aed',
        'ctf-accent': '#06ffa5',
        'ctf-warning': '#ffb800',
        'ctf-danger': '#ff3366',

        // Portal background colors
        'portal-bg-primary': '#0a0a0f',
        'portal-bg-secondary': '#151520',
        'portal-bg-tertiary': '#1a1a2e',
        'portal-bg': '#0a0a0f',
        'portal-bg-alt': '#151520',
        'portal-surface': '#1e1e2e',

        // FinBot app colors
        'bg-primary': '#07070d',
        'bg-secondary': '#0e0e1a',
        'bg-card': '#121220',
        'cyan': '#00d4ff',
        'purple': '#7c3aed',
        'green': '#06ffa5',
        'amber': '#ffb800',
        'danger': '#ff3366',
        'text-1': '#f1f5f9',
        'text-2': '#94a3b8',
        'text-3': '#64748b',
        'border-dim': 'rgba(255,255,255,0.06)',
        'border-glow': 'rgba(0,212,255,0.25)',

        // Command Center colors
        'cc-bg': '#0c0c14',
        'cc-surface': '#12121e',
        'cc-border': 'rgba(255,255,255,0.06)',

        // Text colors
        'text-primary': '#e2e8f0',
        'text-secondary': '#94a3b8',
        'text-bright': '#ffffff',
      },
      fontFamily: {
        'display': ['Playfair Display', 'serif'],
        'sans': ['Inter', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.6s ease-out',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite alternate',

        // Error page animations
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 3s infinite',
        'bounce-slow': 'bounce 2s infinite',
        'wiggle': 'wiggle 1s ease-in-out infinite',
        'shake': 'shake 0.5s ease-in-out infinite',
        'spin-slow': 'spin 3s linear infinite',
        'glitch': 'glitch 2s infinite',
        'flicker': 'flicker 1.5s infinite',
        'sleep': 'sleep 3s ease-in-out infinite',
        'snore': 'snore 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(212, 175, 55, 0.5)' },
          '100%': { boxShadow: '0 0 20px rgba(212, 175, 55, 1)' },
        },
        
        // Error page keyframes
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        wiggle: {
          '0%, 100%': { transform: 'rotate(-3deg)' },
          '50%': { transform: 'rotate(3deg)' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-2px)' },
          '20%, 40%, 60%, 80%': { transform: 'translateX(2px)' },
        },
        glitch: {
          '0%, 100%': { transform: 'translate(0)' },
          '20%': { transform: 'translate(-2px, 2px)' },
          '40%': { transform: 'translate(-2px, -2px)' },
          '60%': { transform: 'translate(2px, 2px)' },
          '80%': { transform: 'translate(2px, -2px)' },
        },
        flicker: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        sleep: {
          '0%, 100%': { transform: 'rotate(-2deg)' },
          '50%': { transform: 'rotate(2deg)' },
        },
        snore: {
          '0%, 100%': { opacity: '0.3', transform: 'scale(0.8)' },
          '50%': { opacity: '1', transform: 'scale(1.2)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
        glowPulse: {
          '0%': { boxShadow: '0 0 5px rgba(0, 212, 255, 0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(0, 212, 255, 0.6)' },
        },
      },
      zIndex: {
        '60': '60',
        '70': '70',
      },
    },
  },
  plugins: [],
}
