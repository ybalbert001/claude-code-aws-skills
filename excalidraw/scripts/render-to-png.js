#!/usr/bin/env node

/**
 * Excalidraw to PNG Renderer
 *
 * Converts Excalidraw JSON files to PNG images using Playwright to render
 * the diagram in a headless browser.
 *
 * Prerequisites:
 *   npm install playwright
 *   npx playwright install chromium
 *
 * Usage:
 *   node render-to-png.js <input.excalidraw.json> [output.png] [options]
 *
 * Options:
 *   --padding <number>      Padding around diagram (default: 50)
 *   --background <color>    Background color (default: #ffffff)
 *   --theme <light|dark>    Theme mode (default: light)
 *   --scale <number>        Scale factor for higher resolution (default: 2)
 */

const fs = require('fs');
const path = require('path');

async function renderExcalidrawToPNG(inputPath, outputPath, options = {}) {
  let playwright;

  try {
    playwright = require('playwright');
  } catch (error) {
    console.error('\nError: Playwright is not installed.');
    console.error('\nTo install Playwright, run:');
    console.error('  npm install playwright');
    console.error('  npx playwright install chromium\n');
    process.exit(1);
  }

  // Read and validate the Excalidraw JSON file
  let excalidrawData;
  try {
    const fileContent = fs.readFileSync(inputPath, 'utf8');
    excalidrawData = JSON.parse(fileContent);
  } catch (error) {
    console.error(`Error reading or parsing file: ${error.message}`);
    process.exit(1);
  }

  const elements = excalidrawData.elements || [];
  if (elements.length === 0) {
    console.warn('Warning: No elements found in Excalidraw file');
  }

  // Create HTML content with Excalidraw viewer
  const htmlContent = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@excalidraw/excalidraw@0.18.0/dist/excalidraw.production.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { overflow: hidden; }
    #app { width: 100vw; height: 100vh; }
  </style>
</head>
<body>
  <div id="app"></div>
  <script>
    const excalidrawData = ${JSON.stringify(excalidrawData)};

    const App = () => {
      const excalidrawRef = React.useRef(null);

      React.useEffect(() => {
        // Signal readiness after render
        setTimeout(() => { window.diagramReady = true; }, 500);
      }, []);

      return React.createElement(
        ExcalidrawLib.Excalidraw,
        {
          ref: excalidrawRef,
          initialData: {
            elements: excalidrawData.elements || [],
            appState: {
              ...(excalidrawData.appState || {}),
              viewBackgroundColor: '${options.backgroundColor || '#ffffff'}',
              theme: '${options.theme || 'light'}',
              zoom: { value: 1 },
            },
            scrollToContent: true,
          },
          viewModeEnabled: true,
          zenModeEnabled: true,
        }
      );
    };

    const root = ReactDOM.createRoot(document.getElementById('app'));
    root.render(React.createElement(App));
  </script>
</body>
</html>
  `;

  // Calculate viewport dimensions based on element bounds
  let bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };

  elements.forEach(element => {
    if (element.isDeleted) return;

    const right = element.x + (element.width || 0);
    const bottom = element.y + (element.height || 0);

    bounds.minX = Math.min(bounds.minX, element.x);
    bounds.minY = Math.min(bounds.minY, element.y);
    bounds.maxX = Math.max(bounds.maxX, right);
    bounds.maxY = Math.max(bounds.maxY, bottom);
  });

  // Fallback dimensions if no valid bounds
  if (!isFinite(bounds.minX)) {
    bounds = { minX: 0, minY: 0, maxX: 800, maxY: 600 };
  }

  const padding = options.padding || 50;
  const scale = options.scale || 2;
  const width = Math.max(400, Math.ceil(bounds.maxX - bounds.minX + padding * 2));
  const height = Math.max(300, Math.ceil(bounds.maxY - bounds.minY + padding * 2));

  // Launch browser and capture screenshot
  console.log('Launching browser...');
  const browser = await playwright.chromium.launch({ headless: true });

  try {
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: scale,
    });

    const page = await context.newPage();

    console.log('Rendering diagram...');
    await page.setContent(htmlContent, { waitUntil: 'networkidle' });

    // Wait for Excalidraw to be ready
    await page.waitForFunction(() => window.diagramReady, { timeout: 10000 });

    // Additional stabilization time
    await page.waitForTimeout(1000);

    // Capture screenshot
    await page.screenshot({
      path: outputPath,
      type: 'png',
    });

    console.log(`\n✓ PNG rendered successfully`);
    console.log(`  Output: ${outputPath}`);
    console.log(`  Dimensions: ${width}x${height}px (${scale}x scale)`);
    console.log(`  Elements: ${elements.filter(e => !e.isDeleted).length}\n`);

    await context.close();
    return { success: true, outputPath, width, height };
  } catch (error) {
    console.error(`\nError during rendering: ${error.message}\n`);
    throw error;
  } finally {
    await browser.close();
  }
}

// CLI entry point
if (require.main === module) {
  const args = process.argv.slice(2);

  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    console.log(`
Excalidraw to PNG Renderer

Converts Excalidraw JSON files to PNG images.

Usage:
  node render-to-png.js <input.excalidraw.json> [output.png] [options]

Arguments:
  input.excalidraw.json   Path to Excalidraw JSON file (required)
  output.png              Output PNG path (optional, defaults to input name)

Options:
  --padding <number>      Padding around diagram in pixels (default: 50)
  --background <color>    Background color (default: #ffffff)
  --theme <light|dark>    Theme mode (default: light)
  --scale <number>        Scale factor for resolution (default: 2)

Examples:
  node render-to-png.js diagram.excalidraw.json
  node render-to-png.js diagram.excalidraw.json output.png
  node render-to-png.js diagram.json output.png --padding 100 --scale 3
  node render-to-png.js diagram.json out.png --background transparent --theme dark

Prerequisites:
  npm install playwright
  npx playwright install chromium
    `);
    process.exit(0);
  }

  const inputPath = path.resolve(args[0]);

  // Determine output path
  let outputPath;
  if (args[1] && !args[1].startsWith('--')) {
    outputPath = path.resolve(args[1]);
  } else {
    outputPath = inputPath.replace(/\.excalidraw(\.json)?$/i, '.png');
  }

  // Parse options
  const options = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--padding' && args[i + 1]) {
      options.padding = parseInt(args[i + 1], 10);
    } else if (args[i] === '--background' && args[i + 1]) {
      options.backgroundColor = args[i + 1];
    } else if (args[i] === '--theme' && args[i + 1]) {
      options.theme = args[i + 1];
    } else if (args[i] === '--scale' && args[i + 1]) {
      options.scale = parseFloat(args[i + 1]);
    }
  }

  // Validate input file exists
  if (!fs.existsSync(inputPath)) {
    console.error(`\nError: Input file not found: ${inputPath}\n`);
    process.exit(1);
  }

  // Execute rendering
  renderExcalidrawToPNG(inputPath, outputPath, options)
    .catch(error => {
      console.error(`\nFatal error: ${error.message}\n`);
      process.exit(1);
    });
}

module.exports = { renderExcalidrawToPNG };
