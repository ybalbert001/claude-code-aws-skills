/**
 * AWS Dark Theme Configuration
 * 
 * Customize theme colors, fonts, and styles by modifying this file.
 * Changes will be applied globally across all presentations using this theme.
 */

export default {
  // Brand Colors
  colors: {
    // AWS Brand Colors
    orange: '#ff9900',
    blue: '#00a1e0',
    darkBlue: '#232f3e',
    lightBlue: '#2e6db5',
    purple: '#9d4edd',
    green: '#00d4aa',
    
    // Background & Text
    background: '#000000',          // Main slide background (pure black)
    text: '#ffffff',                 // Main text color
    textSecondary: '#e0e0e0',       // Secondary text (footer, etc.)
    
    // Gradient Colors (for cover, section, end slides)
    gradientStart: '#232f3e',       // Dark blue
    gradientEnd: '#00a1e0',         // AWS blue
  },
  
  // Predefined Gradient Backgrounds
  gradients: {
    // AWS Default: Blue to Purple
    awsDefault: 'linear-gradient(135deg, #0a2540 0%, #1a4d7a 40%, #2e6db5 60%, #7b3f9e 80%, #9d4edd 100%)',
    
    // AWS Blue: Dark blue to light blue
    awsBlue: 'linear-gradient(135deg, #232f3e 0%, #00a1e0 100%)',
    
    // AWS Orange: Dark to orange
    awsOrange: 'linear-gradient(135deg, #232f3e 0%, #ff9900 100%)',
    
    // AWS Green: Dark to green
    awsGreen: 'linear-gradient(135deg, #232f3e 0%, #00d4aa 100%)',
    
    // AWS Purple: Dark blue to purple
    awsPurple: 'linear-gradient(135deg, #232f3e 0%, #9d4edd 100%)',
    
    // Ocean: Blue gradient
    ocean: 'linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%)',
    
    // Sunset: Orange to pink
    sunset: 'linear-gradient(135deg, #ff6b35 0%, #f7931e 50%, #c9184a 100%)',
    
    // Forest: Green gradient
    forest: 'linear-gradient(135deg, #1b4332 0%, #2d6a4f 50%, #52b788 100%)',
    
    // Night: Dark blue gradient
    night: 'linear-gradient(135deg, #0d1b2a 0%, #1b263b 50%, #415a77 100%)',
    
    // Fire: Red to orange
    fire: 'linear-gradient(135deg, #7f1d1d 0%, #dc2626 50%, #f97316 100%)',
    
    // Royal: Purple gradient
    royal: 'linear-gradient(135deg, #4c1d95 0%, #7c3aed 50%, #a78bfa 100%)',
    
    // Tech: Cyan to blue
    tech: 'linear-gradient(135deg, #0e7490 0%, #0284c7 50%, #3b82f6 100%)',
  },
  
  // Typography
  typography: {
    // Font Family
    fontFamily: "'Amazon Ember', 'Helvetica Neue', Arial, sans-serif",
    
    // Font Sizes (in rem)
    fontSize: {
      h1: '3rem',      // Main titles
      h2: '2rem',      // Section titles
      h3: '1.5rem',    // Subsection titles
      p: '1.125rem',   // Paragraph text
      small: '0.875rem', // Small text
      footer: '0.5rem',  // Footer text
    },
    
    // Font Weights
    fontWeight: {
      normal: 400,
      semibold: 600,
      bold: 700,
    },
    
    // Line Heights
    lineHeight: {
      tight: 1.2,
      normal: 1.6,
      relaxed: 1.8,
    },
  },
  
  // Layout Spacing
  spacing: {
    padding: '2.5rem 3rem 1.5rem 3rem', // Slide padding (top right bottom left)
    gap: '3rem',                         // Gap between columns
    marginBottom: {
      h1: '2rem',
      h2: '1.5rem',
      h3: '1rem',
      p: '1rem',
    },
  },
  
  // Footer Configuration
  footer: {
    show: true,
    logoSize: 'sm',        // 'sm', 'md', 'lg', 'xl'
    logoColor: '#e0e0e0',
    textColor: '#e0e0e0',
    fontSize: '0.5rem',
    pageNumberSize: '0.75rem',
  },
  
  // Diagram Styles (Mermaid)
  diagram: {
    lineColor: '#ffffff',
    lineWidth: '2px',
    nodeStroke: '#ffffff',
    nodeStrokeWidth: '2px',
    nodeFill: 'transparent',
    textColor: '#ffffff',
    fontSize: '14px',
  },
}
